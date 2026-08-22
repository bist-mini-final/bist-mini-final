from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final

from backend.llm.chat_completion import ChatCompletionClient
from backend.storage.pgvector_store import PgVectorStore

from .api_services import BiApiServices
from .document_profiler import BiDocumentProfiler
from .extraction import BiMetricExtractionService
from .fast_rag_adapter import FastRagPipelineAdapter
from .initial_snapshot import (
    BiInitialSnapshotMaterializer,
    BiInitialSnapshotServices,
)
from .materializer import SystemClock
from .metric_reader import BiMetricReader, ExistingChatCompletionAdapter
from .question_pipeline import BiQuestionPipeline, PgVectorQuestionSourceResolver
from .profile_repository import (
    PersistedBiDocumentProfiler,
    PostgresBiDocumentProfileRepository,
)
from .profile_sheet_catalog import (
    PostgresBiProfileEvidenceRetriever,
    PostgresBiProfileSheetCatalog,
)
from .question_repository import PostgresBiQuestionRepository
from .queued_materializer import BiQueuedMaterializer, BiQueuedMaterializerServices
from .question_service import BiQuestionService
from .question_snapshot import (
    BiPublishingQuestionService,
    BiQuestionSnapshotMaterializer,
    BiQuestionSnapshotMaterializerServices,
)
from .question_snapshot_repository import PostgresBiQuestionSnapshotRepository
from .question_worker import BiQuestionWorker, SystemBiQuestionWorkerClock
from .snapshot_store import DEFAULT_BI_ARTIFACT_DIR, FileBiSnapshotStore

if TYPE_CHECKING:
    from backend.runtime.registry import ModuleRegistry


BI_READER_MODEL: Final = "gpt-5.6-luna"


def create_bi_services(
    registry: ModuleRegistry,
    completion_client: ChatCompletionClient | None = None,
    artifact_dir: Path = DEFAULT_BI_ARTIFACT_DIR,
) -> BiApiServices:
    clock = SystemClock()
    store = FileBiSnapshotStore(artifact_dir)
    store.fail_interrupted_jobs(clock.now())
    pgvector_store = PgVectorStore()
    retriever = FastRagPipelineAdapter(registry, pgvector_store)
    completion = ExistingChatCompletionAdapter(
        completion_client or ChatCompletionClient()
    )
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
    questions = create_bi_question_service()
    runner = BiQueuedMaterializer(
        BiQueuedMaterializerServices(
            profiler=profiler,
            questions=questions,
            store=store,
            clock=clock,
        )
    )
    persisted_answers = PostgresBiQuestionSnapshotRepository()
    initial_snapshots = BiInitialSnapshotMaterializer(
        BiInitialSnapshotServices(
            answers=persisted_answers,
            source_resolver=PgVectorQuestionSourceResolver(pgvector_store),
            profiles=profiles,
            store=store,
            clock=clock,
        )
    )
    return BiApiServices(
        store=store,
        runner=runner,
        clock=clock,
        questions=questions,
        initial_snapshots=initial_snapshots,
    )


def create_bi_question_pipeline(
    registry: ModuleRegistry,
    completion_client: ChatCompletionClient | None = None,
) -> BiQuestionPipeline:
    pgvector_store = PgVectorStore()
    retriever = FastRagPipelineAdapter(registry, pgvector_store)
    completion = ExistingChatCompletionAdapter(
        completion_client or ChatCompletionClient()
    )
    extractor = BiMetricExtractionService(
        retriever,
        BiMetricReader(completion, BI_READER_MODEL),
    )
    return BiQuestionPipeline(
        extractor,
        PgVectorQuestionSourceResolver(pgvector_store),
    )


def create_bi_question_service() -> BiQuestionService:
    return BiQuestionService(PostgresBiQuestionRepository())


def create_bi_question_worker(
    registry: ModuleRegistry,
    completion_client: ChatCompletionClient | None = None,
) -> BiQuestionWorker:
    service = create_bi_question_service()
    snapshot_materializer = BiQuestionSnapshotMaterializer(
        BiQuestionSnapshotMaterializerServices(
            questions=service,
            answers=PostgresBiQuestionSnapshotRepository(),
            store=FileBiSnapshotStore(),
            clock=SystemClock(),
        )
    )
    return BiQuestionWorker(
        BiPublishingQuestionService(service, snapshot_materializer),
        create_bi_question_pipeline(registry, completion_client),
        SystemBiQuestionWorkerClock(),
    )
