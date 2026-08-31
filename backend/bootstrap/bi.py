from __future__ import annotations

from typing import TYPE_CHECKING, Final

from backend.domains.bi.application import BiApiServices
from backend.domains.bi.application.document_profiler import BiDocumentProfiler
from backend.domains.bi.application.extraction import BiMetricExtractionService
from backend.domains.bi.application.materializer import SystemClock
from backend.domains.bi.application.metric_reader import BiMetricReader
from backend.domains.bi.application.profile_persistence import PersistedBiDocumentProfiler
from backend.domains.bi.application.question_publishing import (
    BiPublishingQuestionService,
    BiQuestionPublicationFailureReporter,
)
from backend.domains.bi.application.question_service import BiQuestionService
from backend.domains.bi.application.question_snapshot import (
    BiQuestionSnapshotMaterializer,
    BiQuestionSnapshotMaterializerServices,
)
from backend.domains.bi.application.queued_materializer import (
    BiQueuedMaterializer,
    BiQueuedMaterializerServices,
)
from backend.domains.bi.infrastructure.integrations.fast_rag_adapter import FastRagPipelineAdapter
from backend.domains.bi.infrastructure.integrations.question_pipeline import (
    BiQuestionPipeline,
    PgVectorQuestionSourceResolver,
)
from backend.domains.bi.infrastructure.integrations.structured_completion import (
    BiStructuredCompletionAdapter,
)
from backend.domains.bi.infrastructure.integrations.workbook_profiles import (
    WorkbookBiProfileRepository,
)
from backend.domains.bi.infrastructure.postgres.metric_evidence import (
    PostgresBiMetricEvidenceRetriever,
)
from backend.domains.bi.infrastructure.postgres.profile_sheet_catalog import (
    PostgresBiProfileEvidenceRetriever,
    PostgresBiProfileSheetCatalog,
)
from backend.domains.bi.infrastructure.postgres.question_repository import (
    PostgresBiQuestionRepository,
)
from backend.domains.bi.infrastructure.postgres.question_snapshot_repository import (
    PostgresBiQuestionSnapshotRepository,
)
from backend.domains.bi.infrastructure.postgres.store import PostgresBiStore
from backend.domains.bi.workers.question import BiQuestionWorker, SystemBiQuestionWorkerClock
from backend.domains.bi.workers.question_batch import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_MAX_WORKERS,
    BiQuestionBatchWorker,
    SystemBiQuestionBatchWorkerClock,
)
from backend.domains.data_sources.infrastructure.postgres.workbook_profiles import (
    PostgresWorkbookProfileRepository,
)
from backend.domains.data_sources.infrastructure.spreadsheets.workbook_profile_extractor import (
    WORKBOOK_PROFILE_VERSION,
)
from backend.domains.data_sources.infrastructure.workbook_profile_resolver import (
    StoredWorkbookProfileResolver,
)
from backend.platform.openai.responses import OpenAIResponsesClient

if TYPE_CHECKING:
    from backend.bootstrap.module_registry import ModuleRegistry


BI_READER_MODEL: Final = "gpt-5.6-luna"


def _create_bi_profiles(registry: ModuleRegistry) -> WorkbookBiProfileRepository:
    return WorkbookBiProfileRepository(
        profiles=PostgresWorkbookProfileRepository(registry.database_url),
        resolver=StoredWorkbookProfileResolver(registry.database_url),
        profile_version=WORKBOOK_PROFILE_VERSION,
    )


def create_bi_services(
    registry: ModuleRegistry,
) -> BiApiServices:
    clock = SystemClock()
    store = PostgresBiStore(registry.database_url)
    questions = create_bi_question_service()
    return BiApiServices(
        store=store,
        materializations=store,
        clock=clock,
        questions=questions,
    )


def create_bi_materialization_runner(
    registry: ModuleRegistry,
    completion_client: OpenAIResponsesClient,
) -> BiQueuedMaterializer:
    clock = SystemClock()
    store = PostgresBiStore(registry.database_url)
    completion = BiStructuredCompletionAdapter(completion_client)
    profiles = _create_bi_profiles(registry)
    profiler = PersistedBiDocumentProfiler(
        BiDocumentProfiler(
            PostgresBiProfileEvidenceRetriever(),
            completion,
            BI_READER_MODEL,
            PostgresBiProfileSheetCatalog(),
        ),
        profiles,
        clock,
    )
    return BiQueuedMaterializer(
        BiQueuedMaterializerServices(
            profiler=profiler,
            questions=create_bi_question_service(),
            store=store,
            clock=clock,
        )
    )


def create_bi_question_pipeline(
    registry: ModuleRegistry,
    completion_client: OpenAIResponsesClient,
) -> BiQuestionPipeline:
    pgvector_store = registry.pgvector_store
    retriever = FastRagPipelineAdapter(
        registry,
        pgvector_store,
        metric_evidence=PostgresBiMetricEvidenceRetriever(registry.database_url),
    )
    completion = BiStructuredCompletionAdapter(completion_client)
    extractor = BiMetricExtractionService(
        retriever,
        BiMetricReader(completion, BI_READER_MODEL),
        _create_bi_profiles(registry),
    )
    return BiQuestionPipeline(
        extractor,
        PgVectorQuestionSourceResolver(pgvector_store),
    )


def create_bi_question_service() -> BiQuestionService:
    return BiQuestionService(PostgresBiQuestionRepository())


def create_bi_question_worker(
    registry: ModuleRegistry,
    completion_client: OpenAIResponsesClient,
) -> BiQuestionWorker:
    """
    Create a BI question worker with PostgreSQL persistence and snapshot materialization.
    
    Parameters:
        registry (ModuleRegistry): Application registry providing database configuration and retrieval dependencies.
        completion_client (OpenAIResponsesClient): Client used to generate structured question responses.
    
    Returns:
        BiQuestionWorker: Configured worker for processing and publishing BI questions.
    """
    service = create_bi_question_service()
    store = PostgresBiStore(registry.database_url)
    snapshot_materializer = BiQuestionSnapshotMaterializer(
        BiQuestionSnapshotMaterializerServices(
            questions=service,
            answers=PostgresBiQuestionSnapshotRepository(),
            store=store,
            clock=SystemClock(),
            profiles=_create_bi_profiles(registry),
        )
    )
    return BiQuestionWorker(
        BiPublishingQuestionService(
            service,
            snapshot_materializer,
            BiQuestionPublicationFailureReporter(service, store, SystemClock()),
        ),
        create_bi_question_pipeline(registry, completion_client),
        SystemBiQuestionWorkerClock(),
    )


def create_bi_question_batch_worker(
    registry: ModuleRegistry,
    completion_client: OpenAIResponsesClient,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_workers: int = DEFAULT_MAX_WORKERS,
) -> BiQuestionBatchWorker:
    """
    Create a worker that processes BI questions in configurable batches and publishes refreshed snapshots.
    
    Parameters:
        batch_size (int): Number of questions claimed per batch.
        max_workers (int): Maximum number of concurrent worker threads.
    
    Returns:
        BiQuestionBatchWorker: Configured batch question worker.
    """
    service = create_bi_question_service()
    store = PostgresBiStore(registry.database_url)
    snapshot_materializer = BiQuestionSnapshotMaterializer(
        BiQuestionSnapshotMaterializerServices(
            questions=service,
            answers=PostgresBiQuestionSnapshotRepository(),
            store=store,
            clock=SystemClock(),
            profiles=_create_bi_profiles(registry),
        )
    )
    publishing_service = BiPublishingQuestionService(
        service,
        snapshot_materializer,
        BiQuestionPublicationFailureReporter(service, store, SystemClock()),
    )
    return BiQuestionBatchWorker(
        publishing_service,
        create_bi_question_pipeline(registry, completion_client),
        SystemBiQuestionBatchWorkerClock(),
        batch_size=batch_size,
        max_workers=max_workers,
    )
