"""Composition root for application services and external adapters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.bootstrap.bi import create_bi_services
from backend.bootstrap.company_comparison import create_company_comparison_service
from backend.bootstrap.runtime import (
    WorkflowRuntimeServices,
    create_workflow_runtime_services,
)
from backend.core.settings import (
    BENCHMARK_SET_DIR,
    CACHE_DIR,
    CHAT_UPLOAD_DIR,
    EMBEDDING_ARTIFACT_DIR,
    KUBERNETES_WORKFLOW_QUEUE,
    PGVECTOR_URL,
    PROCESSED_DATA_DIR,
    RUN_DIR,
    SPREADSHEET_ARTIFACT_DIR,
    WORKFLOW_DIR,
)
from backend.domains.benchmark.application import BenchmarkApplicationService
from backend.domains.benchmark.infrastructure import (
    BenchmarkPostgresStore,
    LocalBenchmarkSetSource,
)
from backend.domains.bi.application import BiApiServices
from backend.domains.chatbot.application import (
    ChatApiServices,
    ChatAttachmentService,
    ChatConversationService,
    ChatSuggestionService,
)
from backend.domains.chatbot.infrastructure.filesystem import LocalChatAttachmentStorage
from backend.domains.chatbot.infrastructure.postgres import (
    ChatSessionRepository,
    ChatSuggestionRepository,
)
from backend.domains.company_comparison.application import CompanyComparisonService
from backend.domains.data_sources.application import (
    CellEvidenceService,
    DataSourceFileService,
    SpreadsheetArtifactService,
)
from backend.domains.data_sources.application.ingestion_jobs import IngestionJobService
from backend.domains.data_sources.application.services import DataSourceApiServices
from backend.domains.data_sources.infrastructure import (
    IngestionSubmissionAdapter,
    PgVectorDatabaseAdapter,
    SourceFileInspectorAdapter,
    SpreadsheetVectorCatalogAdapter,
)
from backend.domains.data_sources.infrastructure.filesystem import (
    LocalSourceFileStorage,
    LocalSpreadsheetArtifactStore,
)
from backend.domains.data_sources.infrastructure.pgvector import PgVectorConnectionProbe
from backend.domains.data_sources.infrastructure.spreadsheets import LocalCellArtifactLocator
from backend.domains.operations.application import OperationsQueryService
from backend.domains.operations.infrastructure import KubernetesMonitor
from backend.domains.workflow.application.execution_service import WorkflowExecutionService
from backend.domains.workflow.infrastructure.kubernetes import KubernetesQueueDispatcher
from backend.platform.openai.embeddings import OpenAIEmbeddingEncoder
from backend.platform.openai.provider import OpenAIProvider
from backend.platform.openai.responses import OpenAIResponsesClient
from backend.shared.application.embeddings import EmbeddingEncoder


@dataclass(frozen=True)
class RuntimePaths:
    benchmark_set_dir: Path = BENCHMARK_SET_DIR
    workflow_dir: Path = WORKFLOW_DIR
    run_dir: Path = RUN_DIR
    cache_dir: Path = CACHE_DIR
    processed_dir: Path = PROCESSED_DATA_DIR
    embedding_artifact_dir: Path = EMBEDDING_ARTIFACT_DIR
    spreadsheet_artifact_dir: Path = SPREADSHEET_ARTIFACT_DIR


@dataclass
class RuntimeContainer:
    """Own shared provider clients and the workflow runtime object graph."""

    openai_provider: OpenAIProvider
    completion_client: OpenAIResponsesClient
    embedding_encoder: EmbeddingEncoder
    services: WorkflowRuntimeServices
    paths: RuntimePaths
    pgvector_probe: PgVectorConnectionProbe
    _owns_openai_provider: bool = True

    @classmethod
    def create(
        cls,
        *,
        paths: RuntimePaths | None = None,
        openai_provider: OpenAIProvider | None = None,
        completion_client: OpenAIResponsesClient | None = None,
        embedding_encoder: EmbeddingEncoder | None = None,
        initialize_schema: bool = True,
        require_database: bool = False,
    ) -> "RuntimeContainer":
        runtime_paths = paths or RuntimePaths()
        owns_provider = openai_provider is None
        provider = openai_provider or OpenAIProvider()
        responses = completion_client or OpenAIResponsesClient(provider=provider)
        embeddings = embedding_encoder or OpenAIEmbeddingEncoder(provider=provider)
        services = create_workflow_runtime_services(
            completion_client=responses,
            embedding_encoder=embeddings,
            workflow_dir=runtime_paths.workflow_dir,
            run_dir=runtime_paths.run_dir,
            cache_dir=runtime_paths.cache_dir,
            processed_dir=runtime_paths.processed_dir,
            embedding_artifact_dir=runtime_paths.embedding_artifact_dir,
            spreadsheet_artifact_dir=runtime_paths.spreadsheet_artifact_dir,
            initialize_schema=initialize_schema,
            require_database=require_database,
        )
        return cls(
            openai_provider=provider,
            completion_client=responses,
            embedding_encoder=embeddings,
            services=services,
            paths=runtime_paths,
            pgvector_probe=PgVectorConnectionProbe(),
            _owns_openai_provider=owns_provider,
        )

    def __enter__(self) -> "RuntimeContainer":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_openai_provider:
            self.openai_provider.close()

    async def aclose(self) -> None:
        if self._owns_openai_provider:
            await self.openai_provider.aclose()


@dataclass
class ExecutionContainer:
    """Own control-plane adapters that schedule durable workflow work."""

    workflow_dispatcher: KubernetesQueueDispatcher
    workflow_execution: WorkflowExecutionService

    @classmethod
    def create(cls, runtime: RuntimeContainer) -> "ExecutionContainer":
        services = runtime.services
        dispatcher = KubernetesQueueDispatcher(
            services.workflow_executor,
            services.run_store,
            KUBERNETES_WORKFLOW_QUEUE,
        )
        return cls(
            workflow_dispatcher=dispatcher,
            workflow_execution=WorkflowExecutionService(
                services.workflow_store,
                services.run_store,
                services.workflow_executor,
                dispatcher,
            ),
        )

    def recover_pending_runs(self) -> int:
        return self.workflow_dispatcher.recover_pending()


@dataclass
class DomainServicesContainer:
    """Own product-facing services without HTTP or process lifecycle concerns."""

    bi_services: BiApiServices
    benchmark: BenchmarkApplicationService
    company_comparison: CompanyComparisonService
    chatbot: ChatApiServices
    data_sources: DataSourceApiServices
    operations: OperationsQueryService

    @property
    def chat_suggestions(self) -> ChatSuggestionService:
        """Compatibility view for lifecycle refresh hooks."""

        return self.chatbot.suggestions

    @property
    def job_monitor(self) -> OperationsQueryService:
        """Compatibility view for the former job monitor service name."""

        return self.operations

    @classmethod
    def create(
        cls,
        runtime: RuntimeContainer,
        execution: ExecutionContainer,
    ) -> "DomainServicesContainer":
        bi_services = create_bi_services(runtime.services.module_registry)
        ingestion = IngestionJobService(
            runtime.services.workflow_store,
            runtime.services.run_store,
            runtime.services.workflow_executor,
            execution.workflow_dispatcher,
        )
        catalog = SpreadsheetVectorCatalogAdapter(
            runtime.services.pgvector_store,
            runtime.embedding_encoder,
        )
        file_storage = LocalSourceFileStorage(runtime.paths.processed_dir)
        chat_suggestions = ChatSuggestionService(
            ChatSuggestionRepository(runtime.services.database_url),
            bi_services.store,
        )
        return cls(
            bi_services=bi_services,
            benchmark=BenchmarkApplicationService(
                store=BenchmarkPostgresStore(
                    runtime.services.database_url
                ),
                workflow_store=runtime.services.workflow_store,
                run_store=runtime.services.run_store,
                workflow_execution=execution.workflow_execution,
                benchmark_sets=LocalBenchmarkSetSource(
                    runtime.paths.benchmark_set_dir
                ),
                queue_available=runtime.services.run_store.supports_durable_queue,
            ),
            company_comparison=create_company_comparison_service(
                bi_services.store,
                database_url=runtime.services.database_url,
            ),
            chatbot=ChatApiServices(
                conversations=ChatConversationService(
                    repository=ChatSessionRepository(runtime.services.database_url),
                    workflow_store=runtime.services.workflow_store,
                    run_store=runtime.services.run_store,
                    workflow_executor=runtime.services.workflow_executor,
                    workflow_dispatcher=execution.workflow_dispatcher,
                    completion_client=runtime.completion_client,
                    bi_catalog=bi_services.store,
                    execution_logs=runtime.services.workflow_runs,
                ),
                suggestions=chat_suggestions,
                attachments=ChatAttachmentService(
                    LocalChatAttachmentStorage(CHAT_UPLOAD_DIR)
                ),
            ),
            data_sources=DataSourceApiServices(
                processed_dir=runtime.paths.processed_dir,
                configured_database_url=PGVECTOR_URL,
                file_storage=file_storage,
                files=DataSourceFileService(
                    storage=file_storage,
                    metadata=runtime.services.source_files,
                    vector_indexes=runtime.services.pgvector_store,
                    ingestion=IngestionSubmissionAdapter(ingestion),
                    inspector=SourceFileInspectorAdapter(),
                ),
                ingestion=ingestion,
                runs=runtime.services.run_store,
                catalog=catalog,
                database=PgVectorDatabaseAdapter(
                    runtime.services.pgvector_store,
                    runtime.pgvector_probe,
                ),
                evidence=CellEvidenceService(
                    runtime.services.pgvector_store,
                    LocalCellArtifactLocator(
                        runtime.paths.processed_dir,
                        runtime.paths.spreadsheet_artifact_dir,
                    ),
                ),
                artifacts=SpreadsheetArtifactService(
                    LocalSpreadsheetArtifactStore(
                        runtime.paths.spreadsheet_artifact_dir
                    )
                ),
            ),
            operations=OperationsQueryService(
                KubernetesMonitor(queue_reader=runtime.services.workflow_runs)
            ),
        )


@dataclass
class ApplicationContainer:
    """Process-neutral object graph shared by HTTP, CLI, and workers."""

    runtime: RuntimeContainer
    execution: ExecutionContainer
    domain: DomainServicesContainer

    @classmethod
    def create(
        cls,
        *,
        runtime: RuntimeContainer | None = None,
    ) -> "ApplicationContainer":
        shared_runtime = runtime or RuntimeContainer.create(require_database=True)
        execution = ExecutionContainer.create(shared_runtime)
        return cls(
            runtime=shared_runtime,
            execution=execution,
            domain=DomainServicesContainer.create(shared_runtime, execution),
        )

    @property
    def workflow_dispatcher(self) -> KubernetesQueueDispatcher:
        """Compatibility view; new composition code uses ``execution``."""

        return self.execution.workflow_dispatcher

    @property
    def bi_services(self) -> BiApiServices:
        """Compatibility view; new composition code uses ``domain``."""

        return self.domain.bi_services

    @property
    def chat_suggestions(self) -> ChatSuggestionService:
        """Compatibility view; new composition code uses ``domain``."""

        return self.domain.chat_suggestions

    def recover_pending_runs(self) -> int:
        return self.execution.recover_pending_runs()

    def close(self) -> None:
        # Kubernetes runs are durable and may outlive this API process.  In
        # particular, Uvicorn's development reloader calls close() on every
        # code change; cancelling here would turn an unrelated reload into a
        # user-visible "질문 처리가 중지되었습니다" failure.
        self.runtime.close()

    async def aclose(self) -> None:
        # FastAPI owns an event loop and can close AsyncOpenAI/httpx pools cleanly.
        await self.runtime.aclose()


__all__ = [
    "ApplicationContainer",
    "DomainServicesContainer",
    "ExecutionContainer",
    "RuntimeContainer",
    "RuntimePaths",
]
