"""Explicit object graphs for HTTP and Kubernetes worker processes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.core.settings import (
    CACHE_DIR,
    EMBEDDING_ARTIFACT_DIR,
    KUBERNETES_WORKFLOW_QUEUE,
    PROCESSED_DATA_DIR,
    RUN_DIR,
    SPREADSHEET_ARTIFACT_DIR,
    VECTOR_INDEX_DIR,
    WORKFLOW_DIR,
)
from backend.engine.orchestration.kubernetes import KubernetesQueueDispatcher
from backend.engine.runtime.services import (
    WorkflowRuntimeServices,
    create_workflow_runtime_services,
)
from backend.features.bi.api_services import BiApiServices
from backend.features.bi.composition import create_bi_services
from backend.providers.embeddings.openai import OpenAIEmbeddingEncoder
from backend.providers.embeddings.ports import EmbeddingEncoder
from backend.providers.openai_provider import OpenAIProvider
from backend.providers.openai_responses import OpenAIResponsesClient
from backend.storage.pgvector_probe import PgVectorConnectionProbe


@dataclass(frozen=True)
class RuntimePaths:
    workflow_dir: Path = WORKFLOW_DIR
    run_dir: Path = RUN_DIR
    cache_dir: Path = CACHE_DIR
    processed_dir: Path = PROCESSED_DATA_DIR
    embedding_artifact_dir: Path = EMBEDDING_ARTIFACT_DIR
    spreadsheet_artifact_dir: Path = SPREADSHEET_ARTIFACT_DIR
    vector_index_dir: Path = VECTOR_INDEX_DIR


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
            vector_index_dir=runtime_paths.vector_index_dir,
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


@dataclass
class ApplicationContainer:
    """The only composition root used by the FastAPI process."""

    runtime: RuntimeContainer
    workflow_dispatcher: KubernetesQueueDispatcher
    bi_services: BiApiServices

    @classmethod
    def create(
        cls,
        *,
        runtime: RuntimeContainer | None = None,
    ) -> "ApplicationContainer":
        shared_runtime = runtime or RuntimeContainer.create(require_database=True)
        services = shared_runtime.services
        dispatcher = KubernetesQueueDispatcher(
            services.workflow_executor,
            services.run_store,
            KUBERNETES_WORKFLOW_QUEUE,
        )
        registry = services.module_registry
        return cls(
            runtime=shared_runtime,
            workflow_dispatcher=dispatcher,
            bi_services=create_bi_services(registry),
        )

    def recover_pending_runs(self) -> int:
        return self.workflow_dispatcher.recover_pending()

    def close(self) -> None:
        self.workflow_dispatcher.cancel_all()
        self.runtime.close()


__all__ = ["ApplicationContainer", "RuntimeContainer", "RuntimePaths"]
