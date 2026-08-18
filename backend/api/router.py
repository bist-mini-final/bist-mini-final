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
from ..storage.embedding_artifacts import EmbeddingArtifactStore
from ..storage.vector_index import VectorIndexStore
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
    router.include_router(
        create_data_source_router(
            vector_index_dir=vector_index_dir,
            embedding_artifact_dir=embedding_artifact_dir,
            embedding_encoder=embedding_encoder,
        )
    )
    return router
