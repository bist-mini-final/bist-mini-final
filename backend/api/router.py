from pathlib import Path
from typing import Optional, cast

from fastapi import APIRouter

from ..core.settings import (
    CACHE_DIR,
    EMBEDDING_ARTIFACT_DIR,
    PLAYGROUND_MAX_CONCURRENCY,
    PREFECT_DEPLOYMENT_NAME,
    RUN_DIR,
    SPREADSHEET_ARTIFACT_DIR,
    VECTOR_INDEX_DIR,
    WORKFLOW_DIR,
)
from ..embeddings.factory import EmbeddingEncoder
from ..llm.chat_completion import ChatCompletionClient
from ..storage.answer_cache import AnswerCacheRepository
from ..runtime.services import create_workflow_runtime_services
from ..runtime.registry import ModuleRegistry
from ..orchestration.prefect import PrefectIngestionDispatcher
from ..workflows import InteractiveWorkflowDispatcher
from .data_source_routes import create_data_source_router
from .module_routes import create_module_router
from .spreadsheet_artifact_routes import create_spreadsheet_artifact_router
from .workflow_routes import create_workflow_router


def create_api_router(
    repository: AnswerCacheRepository,
    workflow_dir: Path = WORKFLOW_DIR,
    run_dir: Path = RUN_DIR,
    cache_dir: Path = CACHE_DIR,
    embedding_artifact_dir: Path = EMBEDDING_ARTIFACT_DIR,
    spreadsheet_artifact_dir: Path = SPREADSHEET_ARTIFACT_DIR,
    vector_index_dir: Path = VECTOR_INDEX_DIR,
    completion_client: Optional[ChatCompletionClient] = None,
    embedding_encoder: Optional[EmbeddingEncoder] = None,
) -> APIRouter:
    """
    Compose the application's `/api` router with shared services and domain-specific endpoints.
    
    Parameters:
    	repository (AnswerCacheRepository): Repository used for answer caching.
    	workflow_dir (Path): Directory containing workflow definitions.
    	run_dir (Path): Directory used to store workflow runs.
    	cache_dir (Path): Directory used for workflow result caching.
    	embedding_artifact_dir (Path): Directory for embedding artifacts.
    	spreadsheet_artifact_dir (Path): Directory for spreadsheet artifacts.
    	vector_index_dir (Path): Directory for vector indexes.
    	completion_client (Optional[ChatCompletionClient]): Optional chat-completion service.
    	embedding_encoder (Optional[EmbeddingEncoder]): Optional embedding encoder.
    
    Returns:
    	APIRouter: Configured router containing the application's API endpoints.
    """

    router = APIRouter(prefix="/api")
    services = create_workflow_runtime_services(
        repository,
        workflow_dir=workflow_dir,
        run_dir=run_dir,
        cache_dir=cache_dir,
        embedding_artifact_dir=embedding_artifact_dir,
        spreadsheet_artifact_dir=spreadsheet_artifact_dir,
        vector_index_dir=vector_index_dir,
        completion_client=completion_client,
        embedding_encoder=embedding_encoder,
    )
    # Playground execution remains interactive. Long-running Excel ingestion
    # always goes through the independently deployed Prefect flow.
    workflow_dispatcher = InteractiveWorkflowDispatcher(
        services.workflow_executor,
        services.run_store,
        max_workers=PLAYGROUND_MAX_CONCURRENCY,
    )
    ingestion_dispatcher = PrefectIngestionDispatcher(
        services.workflow_executor,
        services.run_store,
        PREFECT_DEPLOYMENT_NAME,
    )
    module_registry = cast(ModuleRegistry, services.module_registry)
    workflow_store = services.workflow_store
    run_store = services.run_store
    workflow_executor = services.workflow_executor
    pgvector_store = services.pgvector_store
    router.include_router(create_module_router(module_registry))
    router.include_router(
        create_spreadsheet_artifact_router(spreadsheet_artifact_dir)
    )
    router.include_router(
        create_workflow_router(
            module_registry,
            workflow_dir=workflow_dir,
            run_dir=run_dir,
            cache_dir=cache_dir,
            workflow_store=workflow_store,
            run_store=run_store,
            workflow_executor=workflow_executor,
            workflow_dispatcher=workflow_dispatcher,
        )
    )
    router.include_router(
        create_data_source_router(
            vector_index_dir=vector_index_dir,
            embedding_artifact_dir=embedding_artifact_dir,
            embedding_encoder=embedding_encoder,
            pgvector_store=pgvector_store,
            module_registry=module_registry,
            workflow_store=workflow_store,
            run_store=run_store,
            workflow_executor=workflow_executor,
            workflow_dispatcher=ingestion_dispatcher,
        )
    )
    return router
