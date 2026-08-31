from __future__ import annotations

from typing import TYPE_CHECKING, Final

from backend.domains.bi.application import BiApiServices
from backend.features.bi.document_profiler import BiDocumentProfiler
from backend.features.bi.extraction import BiMetricExtractionService
from backend.features.bi.fast_rag_adapter import FastRagPipelineAdapter
from backend.features.bi.materializer import SystemClock
from backend.features.bi.metric_reader import BiMetricReader, BiStructuredCompletionAdapter
from backend.features.bi.postgres_store import PostgresBiStore
from backend.features.bi.profile_repository import (
    PersistedBiDocumentProfiler,
    PostgresBiDocumentProfileRepository,
)
from backend.features.bi.profile_sheet_catalog import (
    PostgresBiProfileEvidenceRetriever,
    PostgresBiProfileSheetCatalog,
)
from backend.features.bi.question_batch_worker import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_MAX_WORKERS,
    BiQuestionBatchWorker,
    SystemBiQuestionBatchWorkerClock,
)
from backend.features.bi.question_pipeline import BiQuestionPipeline, PgVectorQuestionSourceResolver
from backend.features.bi.question_publishing import (
    BiPublishingQuestionService,
    BiQuestionPublicationFailureReporter,
)
from backend.features.bi.question_repository import PostgresBiQuestionRepository
from backend.features.bi.question_service import BiQuestionService
from backend.features.bi.question_snapshot import (
    BiQuestionSnapshotMaterializer,
    BiQuestionSnapshotMaterializerServices,
)
from backend.features.bi.question_snapshot_repository import PostgresBiQuestionSnapshotRepository
from backend.features.bi.question_worker import BiQuestionWorker, SystemBiQuestionWorkerClock
from backend.features.bi.queued_materializer import (
    BiQueuedMaterializer,
    BiQueuedMaterializerServices,
)
from backend.platform.openai.responses import OpenAIResponsesClient

if TYPE_CHECKING:
    from backend.bootstrap.module_registry import ModuleRegistry


BI_READER_MODEL: Final = "gpt-5.6-luna"


def create_bi_services(
    registry: ModuleRegistry,
) -> BiApiServices:
    clock = SystemClock()
    store = PostgresBiStore(registry.db_manager.database_url)
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
    store = PostgresBiStore(registry.db_manager.database_url)
    completion = BiStructuredCompletionAdapter(completion_client)
    profiles = PostgresBiDocumentProfileRepository()
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
    retriever = FastRagPipelineAdapter(registry, pgvector_store)
    completion = BiStructuredCompletionAdapter(completion_client)
    extractor = BiMetricExtractionService(
        retriever,
        BiMetricReader(completion, BI_READER_MODEL),
        PostgresBiDocumentProfileRepository(),
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
    store = PostgresBiStore(registry.db_manager.database_url)
    snapshot_materializer = BiQuestionSnapshotMaterializer(
        BiQuestionSnapshotMaterializerServices(
            questions=service,
            answers=PostgresBiQuestionSnapshotRepository(),
            store=store,
            clock=SystemClock(),
            profiles=PostgresBiDocumentProfileRepository(),
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
    store = PostgresBiStore(registry.db_manager.database_url)
    snapshot_materializer = BiQuestionSnapshotMaterializer(
        BiQuestionSnapshotMaterializerServices(
            questions=service,
            answers=PostgresBiQuestionSnapshotRepository(),
            store=store,
            clock=SystemClock(),
            profiles=PostgresBiDocumentProfileRepository(),
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

