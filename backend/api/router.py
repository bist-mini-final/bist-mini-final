from pathlib import Path
from typing import Optional

from fastapi import APIRouter

from ..core.settings import (
    CACHE_DIR,
    EMBEDDING_ARTIFACT_DIR,
    RUN_DIR,
    SPREADSHEET_ARTIFACT_DIR,
    VECTOR_INDEX_DIR,
    WORKFLOW_DIR,
)
from ..embeddings.factory import EmbeddingEncoder
from ..llm.chat_completion import ChatCompletionClient
from ..runtime.registry import ModuleRegistry
from ..storage.answer_cache import AnswerCacheRepository
from ..storage.db_manager import DatabaseManager
from ..storage.embedding_artifacts import EmbeddingArtifactStore
from ..storage.pgvector_store import PgVectorStore
from ..storage.vector_index import VectorIndexStore
from ..workflows import (
    ResultCache,
    RunStore,
    WorkflowExecutor,
    WorkflowRunDispatcher,
    WorkflowStore,
)
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
    pgvector_store = PgVectorStore()
    db_manager = DatabaseManager()
    module_registry = ModuleRegistry(
        repository,
        completion_client,
        embedding_encoder,
        embedding_artifact_store=EmbeddingArtifactStore(
            embedding_artifact_dir
        ),
        vector_index_store=VectorIndexStore(vector_index_dir),
        pgvector_store=pgvector_store,
        db_manager=db_manager,
        spreadsheet_artifact_dir=spreadsheet_artifact_dir,
    )
    workflow_store = WorkflowStore(workflow_dir)
    run_store = RunStore(run_dir)
    workflow_executor = WorkflowExecutor(
        module_registry,
        run_store,
        ResultCache(cache_dir),
    )
    workflow_dispatcher = WorkflowRunDispatcher(workflow_executor, run_store)
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
            workflow_dispatcher=workflow_dispatcher,
        )
    )
    return router
