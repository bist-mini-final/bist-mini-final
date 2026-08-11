from pathlib import Path
from typing import Optional

from fastapi import APIRouter

from .answer_cache import AnswerCacheRepository
from .chat_completion import ChatCompletionClient
from .embedding_artifacts import EmbeddingArtifactStore
from .vector_index_store import VectorIndexStore
from .api.module_routes import create_module_router
from .api.spreadsheet_artifact_routes import create_spreadsheet_artifact_router
from .api.workflow_routes import create_workflow_router
from .config import (
    CACHE_DIR,
    EMBEDDING_ARTIFACT_DIR,
    RUN_DIR,
    SPREADSHEET_ARTIFACT_DIR,
    VECTOR_INDEX_DIR,
    WORKFLOW_DIR,
)
from .module_registry import ModuleRegistry
from .modules.embedder import EmbeddingEncoder


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
    """Compose domain-specific API routers and shared services."""

    router = APIRouter(prefix="/api")
    module_registry = ModuleRegistry(
        repository,
        completion_client,
        embedding_encoder,
        embedding_artifact_store=EmbeddingArtifactStore(
            embedding_artifact_dir
        ),
        vector_index_store=VectorIndexStore(vector_index_dir),
    )
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
        )
    )
    return router
