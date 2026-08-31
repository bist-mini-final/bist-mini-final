"""Shared construction of workflow runtime services.

The API process and Kubernetes Job worker build the same module graph and
storage adapters. Keeping that wiring here prevents worker images from
drifting away from the HTTP application's execution behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from backend.core.settings import (
    CACHE_DIR,
    EMBEDDING_ARTIFACT_DIR,
    INGESTION_SHARD_POLL_SECONDS,
    INGESTION_SHARD_WAIT_TIMEOUT_SECONDS,
    INGESTION_SHARDS_ENABLED,
    PROCESSED_DATA_DIR,
    RUN_DIR,
    SPREADSHEET_ARTIFACT_DIR,
    WORKFLOW_DIR,
)
from backend.domains.data_sources.application.shard_coordinator import IngestionShardCoordinator
from backend.domains.data_sources.infrastructure.filesystem.embedding_artifacts import (
    EmbeddingArtifactStore,
)
from backend.domains.data_sources.infrastructure.filesystem.shard_artifacts import (
    IngestionShardArtifactStore,
)
from backend.domains.data_sources.infrastructure.pgvector import PgVectorStore
from backend.domains.data_sources.infrastructure.postgres.shards import (
    PostgresIngestionShardRepository,
)
from backend.domains.data_sources.infrastructure.postgres.source_files import (
    PostgresSourceFileRepository,
)
from backend.domains.workflow.application.executor import WorkflowExecutor
from backend.domains.workflow.infrastructure.persistence import ResultCache, RunStore, WorkflowStore
from backend.domains.workflow.infrastructure.postgres import PostgresWorkflowRunRepository
from backend.platform.openai.pricing import calculate_openai_cost
from backend.platform.openai.responses import OpenAIResponsesClient
from backend.platform.postgres import PostgresConnectionProbe
from backend.platform.telemetry.tracing import trace_node_execution
from backend.shared.application.embeddings import EmbeddingEncoder

from .module_registry import ModuleRegistry
from .schema import ensure_application_schema


@dataclass(frozen=True)
class WorkflowRuntimeServices:
    """Services shared by workflow HTTP routes and Kubernetes workers."""

    pgvector_store: PgVectorStore
    database_url: str
    database_probe: PostgresConnectionProbe
    source_files: PostgresSourceFileRepository
    workflow_runs: PostgresWorkflowRunRepository
    module_registry: ModuleRegistry
    workflow_store: WorkflowStore
    run_store: RunStore
    workflow_executor: WorkflowExecutor


def create_workflow_runtime_services(
    *,
    completion_client: OpenAIResponsesClient,
    embedding_encoder: EmbeddingEncoder,
    workflow_dir: Path = WORKFLOW_DIR,
    run_dir: Path = RUN_DIR,
    cache_dir: Path = CACHE_DIR,
    processed_dir: Path = PROCESSED_DATA_DIR,
    embedding_artifact_dir: Path = EMBEDDING_ARTIFACT_DIR,
    spreadsheet_artifact_dir: Path = SPREADSHEET_ARTIFACT_DIR,
    pgvector_store: Optional[PgVectorStore] = None,
    database_probe: Optional[PostgresConnectionProbe] = None,
    source_files: Optional[PostgresSourceFileRepository] = None,
    workflow_runs: Optional[PostgresWorkflowRunRepository] = None,
    initialize_schema: bool = True,
    require_database: bool = False,
) -> WorkflowRuntimeServices:
    """Build one consistent workflow runtime for an API or worker process."""

    probe = database_probe or PostgresConnectionProbe()
    database_url = probe.database_url
    source_file_repository = source_files or PostgresSourceFileRepository(database_url)
    workflow_run_repository = workflow_runs or PostgresWorkflowRunRepository(database_url)
    database_connected = probe.is_connected()
    if require_database and not database_connected:
        raise RuntimeError("워크플로 런타임이 PostgreSQL 데이터베이스에 연결할 수 없습니다")
    if database_connected and initialize_schema and not ensure_application_schema(database_url):
        raise RuntimeError("PostgreSQL 워크플로 스키마를 초기화할 수 없습니다")

    pg_store = pgvector_store or PgVectorStore(database_url)
    embedding_store = EmbeddingArtifactStore(embedding_artifact_dir)
    shard_coordinator = IngestionShardCoordinator(
        PostgresIngestionShardRepository(database_url),
        IngestionShardArtifactStore(embedding_store),
        enabled=INGESTION_SHARDS_ENABLED and database_connected,
        pgvector_store=pg_store,
        poll_seconds=INGESTION_SHARD_POLL_SECONDS,
        wait_timeout_seconds=INGESTION_SHARD_WAIT_TIMEOUT_SECONDS,
    )
    registry = ModuleRegistry(
        completion_client=completion_client,
        embedding_encoder=embedding_encoder,
        embedding_artifact_store=embedding_store,
        ingestion_shard_coordinator=shard_coordinator,
        pgvector_store=pg_store,
        source_files=source_file_repository,
        processed_dir=processed_dir,
        spreadsheet_artifact_dir=spreadsheet_artifact_dir,
    )
    workflow_store = WorkflowStore(workflow_dir)
    run_store = RunStore(
        run_dir,
        repository=workflow_run_repository if database_connected else None,
        require_database=require_database,
    )
    workflow_executor = WorkflowExecutor(
        registry,
        run_store,
        ResultCache(cache_dir),
        cost_calculator=calculate_openai_cost,
        node_trace=trace_node_execution,
    )
    return WorkflowRuntimeServices(
        pgvector_store=pg_store,
        database_url=database_url,
        database_probe=probe,
        source_files=source_file_repository,
        workflow_runs=workflow_run_repository,
        module_registry=registry,
        workflow_store=workflow_store,
        run_store=run_store,
        workflow_executor=workflow_executor,
    )
