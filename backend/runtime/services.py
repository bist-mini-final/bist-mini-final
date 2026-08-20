"""Shared construction of workflow runtime services.

The API process and Prefect Flow must build the same module graph and storage
adapters. Keeping that wiring here prevents the Flow image from drifting away
from the HTTP application's execution behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from ..core.settings import (
    CACHE_DIR,
    EMBEDDING_ARTIFACT_DIR,
    PROCESSED_DATA_DIR,
    RUN_DIR,
    SPREADSHEET_ARTIFACT_DIR,
    VECTOR_INDEX_DIR,
    WORKFLOW_DIR,
)
from ..embeddings.factory import EmbeddingEncoder
from ..llm.chat_completion import ChatCompletionClient
from ..storage.answer_cache import AnswerCacheRepository
from ..storage.db_manager import DatabaseManager
from ..storage.embedding_artifacts import EmbeddingArtifactStore
from ..storage.pgvector_store import PgVectorStore
from ..storage.vector_index import VectorIndexStore
from ..workflows.executor import WorkflowExecutor
from ..workflows.store import ResultCache, RunStore, WorkflowStore
from .registry_base import BaseModuleRegistry


@dataclass(frozen=True)
class WorkflowRuntimeServices:
    """Services shared by workflow HTTP routes and Prefect Flows."""

    pgvector_store: PgVectorStore
    db_manager: DatabaseManager
    module_registry: BaseModuleRegistry
    workflow_store: WorkflowStore
    run_store: RunStore
    workflow_executor: WorkflowExecutor


def create_workflow_runtime_services(
    repository: AnswerCacheRepository,
    *,
    workflow_dir: Path = WORKFLOW_DIR,
    run_dir: Path = RUN_DIR,
    cache_dir: Path = CACHE_DIR,
    processed_dir: Path = PROCESSED_DATA_DIR,
    embedding_artifact_dir: Path = EMBEDDING_ARTIFACT_DIR,
    spreadsheet_artifact_dir: Path = SPREADSHEET_ARTIFACT_DIR,
    vector_index_dir: Path = VECTOR_INDEX_DIR,
    completion_client: Optional[ChatCompletionClient] = None,
    embedding_encoder: Optional[EmbeddingEncoder] = None,
    pgvector_store: Optional[PgVectorStore] = None,
    db_manager: Optional[DatabaseManager] = None,
    initialize_schema: bool = True,
    require_database: bool = False,
    registry_factory: Optional[Callable[..., BaseModuleRegistry]] = None,
) -> WorkflowRuntimeServices:
    """Build one consistent workflow runtime for an API or worker process."""

    database = db_manager or DatabaseManager()
    database_connected = database.is_connected()
    if require_database and not database_connected:
        raise RuntimeError("Prefect Flow가 PostgreSQL 데이터베이스에 연결할 수 없습니다")
    if database_connected and initialize_schema and not database.ensure_schema():
        raise RuntimeError("PostgreSQL 워크플로 스키마를 초기화할 수 없습니다")

    pg_store = pgvector_store or PgVectorStore(database.database_url)
    if registry_factory is None:
        # Keep the full application registry out of the ingestion Flow's
        # import and startup path.
        from .registry import ModuleRegistry

        registry_factory = ModuleRegistry
    registry = registry_factory(
        repository,
        completion_client,
        embedding_encoder,
        embedding_artifact_store=EmbeddingArtifactStore(embedding_artifact_dir),
        vector_index_store=VectorIndexStore(vector_index_dir),
        pgvector_store=pg_store,
        db_manager=database,
        processed_dir=processed_dir,
        spreadsheet_artifact_dir=spreadsheet_artifact_dir,
    )
    workflow_store = WorkflowStore(workflow_dir)
    run_store = RunStore(
        run_dir,
        db_manager=database if database_connected else None,
    )
    workflow_executor = WorkflowExecutor(
        registry,
        run_store,
        ResultCache(cache_dir),
    )
    return WorkflowRuntimeServices(
        pgvector_store=pg_store,
        db_manager=database,
        module_registry=registry,
        workflow_store=workflow_store,
        run_store=run_store,
        workflow_executor=workflow_executor,
    )
