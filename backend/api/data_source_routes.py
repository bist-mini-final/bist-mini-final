"""Composition and HTTP route declarations for Data Sources."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from backend.core.settings import PROCESSED_DATA_DIR
from backend.domains.data_sources.application import DataSourceFileService
from backend.domains.workflow.application.dispatching import RunDispatcher
from backend.domains.workflow.application.executor import WorkflowExecutor
from backend.domains.workflow.infrastructure.persistence import RunStore, WorkflowStore
from backend.platform.data_sources import (
    IngestionSubmissionAdapter,
    SourceFileInspectorAdapter,
)
from backend.shared.application.embeddings import EmbeddingEncoder
from backend.storage.data_sources import IngestionJobService
from backend.storage.db_manager import DatabaseManager
from backend.storage.pgvector_probe import PgVectorConnectionProbe
from backend.storage.pgvector_store import PgVectorStore

from .data_source_controller import (
    DataSourceHttpController,
    SearchRequestDTO,
    UpdateIndexCompanyRequestDTO,
)
from .data_source_database_routes import create_database_router
from .data_source_file_routes import create_data_source_file_router
from .data_source_index_routes import create_data_source_index_router
from .data_source_ingestion_routes import create_ingestion_router


def _data_source_controller(
    *,
    processed_dir: Path,
    embedding_encoder: EmbeddingEncoder,
    pgvector_store: PgVectorStore,
    db_manager: DatabaseManager,
    ingestion_jobs: IngestionJobService,
) -> DataSourceHttpController:
    file_service = DataSourceFileService(
        processed_dir=processed_dir,
        metadata=db_manager,
        vector_indexes=pgvector_store,
        ingestion=IngestionSubmissionAdapter(ingestion_jobs),
        inspector=SourceFileInspectorAdapter(),
    )
    return DataSourceHttpController(
        processed_dir=processed_dir,
        file_service=file_service,
        pgvector_store=pgvector_store,
        embedding_encoder=embedding_encoder,
    )


def create_data_source_router(
    *,
    processed_dir: Path = PROCESSED_DATA_DIR,
    embedding_encoder: EmbeddingEncoder,
    pgvector_store: PgVectorStore,
    connection_probe: PgVectorConnectionProbe,
    db_manager: DatabaseManager,
    workflow_store: WorkflowStore,
    run_store: RunStore,
    workflow_executor: WorkflowExecutor,
    workflow_dispatcher: RunDispatcher,
) -> APIRouter:
    """Declare Data Sources endpoints over focused presentation controllers."""
    router = APIRouter(prefix="/data-sources", tags=["데이터 소스 관리"])
    ingestion_jobs = IngestionJobService(
        workflow_store,
        run_store,
        workflow_executor,
        workflow_dispatcher,
    )
    controller = _data_source_controller(
        processed_dir=processed_dir,
        embedding_encoder=embedding_encoder,
        pgvector_store=pgvector_store,
        db_manager=db_manager,
        ingestion_jobs=ingestion_jobs,
    )
    router.include_router(create_database_router(pgvector_store, connection_probe))
    router.include_router(create_ingestion_router(ingestion_jobs, run_store, pgvector_store))
    router.include_router(create_data_source_file_router(controller))
    router.include_router(create_data_source_index_router(controller))

    return router


__all__ = [
    "SearchRequestDTO",
    "UpdateIndexCompanyRequestDTO",
    "create_data_source_router",
]
