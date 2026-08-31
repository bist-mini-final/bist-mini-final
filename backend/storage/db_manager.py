"""Database Manager for full ERD persistence in PostgreSQL.

Documented ERD Schema:
- source_files:
    - file_id (VARCHAR(64), PK): Unique identifier or content hash
    - file_name (VARCHAR(255), NOT NULL): Original name of the source file
    - file_hash (VARCHAR(64), NOT NULL): Content SHA-256 hash
    - file_type (VARCHAR(32), NOT NULL): File extension/format (e.g., excel, parquet, json)
    - file_size (BIGINT, NOT NULL): Size in bytes
    - storage_path (VARCHAR(512), NOT NULL): Path to stored file
    - created_at (TIMESTAMPTZ, DEFAULT NOW()): Record creation timestamp
- sheets:
    - sheet_id (VARCHAR(128), PK): Composite identifier ({file_id}:{sheet_name})
    - file_id (VARCHAR(64), FK -> source_files.file_id): Parent file ID
    - sheet_name (VARCHAR(128), NOT NULL): Sheet name
    - sheet_index (INT, NOT NULL): Index order of the sheet
    - is_visible (BOOLEAN, DEFAULT TRUE): Sheet visibility flag
    - row_count (INT, DEFAULT 0): Total rows in sheet
    - column_count (INT, DEFAULT 0): Total columns in sheet
    - detected_tables (JSONB, DEFAULT '[]'): Detected table boundary metadata
    - parsed_at (TIMESTAMPTZ, DEFAULT NOW()): Parsing timestamp
- langchain_pg_collection:
    - uuid (UUID, PK): Unique identifier for pgvector collection
    - name (VARCHAR, UNIQUE NOT NULL): Collection/Index name
    - cmetadata (JSON): Collection metadata
- langchain_pg_embedding:
    - id (VARCHAR, PK): Chunk embedding ID (UUID or scoped composite ID)
    - collection_id (UUID, FK -> langchain_pg_collection.uuid): Parent collection
    - embedding (vector): Dynamic embedding vector representation (HNSW indexable)
    - document (VARCHAR): Document chunk text content
    - cmetadata (JSONB): Chunk metadata (cell coordinates, headers, etc.)
"""

from __future__ import annotations

import logging
from typing import Any

from backend.core.settings import PGVECTOR_URL
from backend.platform.postgres.audit_schema import AUDIT_SCHEMA_SQL, SOURCE_FILE_AUDIT_SQL
from backend.platform.postgres.repositories import SyncPostgresRepository

from .connection_pool import get_pooled_async_connection
from .repositories import (
    SourceFileRepositoryMixin,
    WorkflowLeaseLost,
    WorkflowRunAlreadyClaimed,
    WorkflowRunLease,
    WorkflowRunRepositoryMixin,
)

logger = logging.getLogger(__name__)

__all__ = [
    "DatabaseManager",
    "WorkflowLeaseLost",
    "WorkflowRunAlreadyClaimed",
    "WorkflowRunLease",
]


DDL_INIT = (
    """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS source_files (
    file_id VARCHAR(64) PRIMARY KEY,
    file_name VARCHAR(255) NOT NULL,
    file_hash VARCHAR(64) NOT NULL,
    file_type VARCHAR(32) NOT NULL,
    file_size BIGINT NOT NULL,
    storage_path VARCHAR(512) NOT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE source_files ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE source_files ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS sheets (
    sheet_id VARCHAR(128) PRIMARY KEY,
    file_id VARCHAR(64) REFERENCES source_files(file_id) ON DELETE CASCADE,
    sheet_name VARCHAR(128) NOT NULL,
    sheet_index INT NOT NULL,
    is_visible BOOLEAN DEFAULT TRUE,
    row_count INT NOT NULL DEFAULT 0,
    column_count INT NOT NULL DEFAULT 0,
    detected_tables JSONB DEFAULT '[]',
    parsed_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS langchain_pg_collection (
    uuid UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR NOT NULL UNIQUE,
    cmetadata JSON
);

CREATE TABLE IF NOT EXISTS langchain_pg_embedding (
    id VARCHAR PRIMARY KEY,
    collection_id UUID REFERENCES langchain_pg_collection(uuid) ON DELETE CASCADE,
    embedding vector,
    document VARCHAR,
    cmetadata JSONB
);

CREATE TABLE IF NOT EXISTS workflow_runs (
    run_id VARCHAR(64) PRIMARY KEY,
    workflow_id VARCHAR(64) NOT NULL,
    workflow_updated_at VARCHAR(64),
    status VARCHAR(32) NOT NULL,
    schema_version INT NOT NULL DEFAULT 2,
    graph JSONB NOT NULL DEFAULT '{}',
    runtime_inputs JSONB NOT NULL DEFAULT '{}',
    use_cache BOOLEAN DEFAULT TRUE,
    orchestration JSONB NOT NULL DEFAULT '{}',
    queue_name VARCHAR(64),
    worker_id VARCHAR(128),
    lease_token VARCHAR(64),
    priority INT NOT NULL DEFAULT 0,
    attempt_count INT NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    claimed_at TIMESTAMPTZ,
    heartbeat_at TIMESTAMPTZ,
    cancel_requested BOOLEAN NOT NULL DEFAULT FALSE,
    batches JSONB NOT NULL DEFAULT '[]',
    nodes JSONB NOT NULL DEFAULT '{}',
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS ingestion_shards (
    operation_id VARCHAR(128) NOT NULL,
    phase VARCHAR(32) NOT NULL CHECK (phase IN ('embedding', 'vector_copy')),
    shard_index INT NOT NULL CHECK (shard_index >= 0),
    status VARCHAR(32) NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
    payload JSONB NOT NULL,
    worker_id VARCHAR(128),
    lease_token VARCHAR(64),
    attempt_count INT NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    claimed_at TIMESTAMPTZ,
    heartbeat_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    total_tokens BIGINT,
    duration_seconds DOUBLE PRECISION,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (operation_id, phase, shard_index)
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id VARCHAR(64) PRIMARY KEY,
    client_id VARCHAR(128) NOT NULL,
    title VARCHAR(160) NOT NULL DEFAULT '새 대화',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS chat_messages (
    message_id VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
    role VARCHAR(16) NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    status VARCHAR(16) NOT NULL CHECK (status IN ('processing', 'completed', 'failed')),
    workflow_run_id VARCHAR(64),
    visualization JSONB,
    attachments JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS visualization JSONB;
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS attachments JSONB NOT NULL DEFAULT '[]';
CREATE INDEX IF NOT EXISTS idx_chat_sessions_client ON chat_sessions(client_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_messages_run ON chat_messages(workflow_run_id) WHERE workflow_run_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS chat_attachments (
    attachment_id VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
    file_name VARCHAR(255) NOT NULL,
    content_type VARCHAR(128),
    file_size BIGINT NOT NULL,
    storage_path VARCHAR(512) NOT NULL,
    extracted_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_chat_attachments_session ON chat_attachments(session_id, created_at);

CREATE TABLE IF NOT EXISTS chat_suggested_questions (
    suggestion_date DATE NOT NULL,
    position SMALLINT NOT NULL,
    question VARCHAR(300) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (suggestion_date, position)
);

-- CREATE TABLE IF NOT EXISTS does not add columns to an existing installation.
ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS orchestration JSONB NOT NULL DEFAULT '{}';
ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS queue_name VARCHAR(64);
ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS worker_id VARCHAR(128);
ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS lease_token VARCHAR(64);
ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS priority INT NOT NULL DEFAULT 0;
ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS attempt_count INT NOT NULL DEFAULT 0;
ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS available_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ;
ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMPTZ;
ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS cancel_requested BOOLEAN NOT NULL DEFAULT FALSE;
CREATE TABLE IF NOT EXISTS node_execution_logs (
    log_id VARCHAR(128) PRIMARY KEY,
    run_id VARCHAR(64) REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
    node_id VARCHAR(128) NOT NULL,
    module_type VARCHAR(64) NOT NULL,
    batch_index INT DEFAULT 0,
    status VARCHAR(32) NOT NULL,
    input_payload JSONB,
    config_payload JSONB DEFAULT '{}',
    output JSONB,
    error TEXT,
    cache_hit BOOLEAN DEFAULT FALSE,
    outcome VARCHAR(32),
    progress JSONB DEFAULT '{}',
    elapsed_ms FLOAT,
    cost_usd FLOAT,
    usage JSONB,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_source_files_hash ON source_files(file_hash);
CREATE INDEX IF NOT EXISTS idx_source_files_active
    ON source_files(created_at DESC) WHERE is_deleted = FALSE;
CREATE INDEX IF NOT EXISTS idx_sheets_file_id ON sheets(file_id);
CREATE INDEX IF NOT EXISTS idx_langchain_cmetadata_gin ON langchain_pg_embedding USING gin (cmetadata jsonb_path_ops);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_workflow_id ON workflow_runs(workflow_id);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_status ON workflow_runs(status);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_updated_at ON workflow_runs(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_queue_claim
    ON workflow_runs(queue_name, status, available_at, priority DESC, created_at)
    WHERE cancel_requested = FALSE;
CREATE INDEX IF NOT EXISTS idx_workflow_runs_stale_lease
    ON workflow_runs(queue_name, heartbeat_at)
    WHERE status = 'running' AND cancel_requested = FALSE;
CREATE INDEX IF NOT EXISTS idx_ingestion_shards_claim
    ON ingestion_shards(phase, status, available_at, created_at)
    WHERE status IN ('queued', 'running');
CREATE INDEX IF NOT EXISTS idx_node_logs_run_id ON node_execution_logs(run_id);
CREATE INDEX IF NOT EXISTS idx_node_logs_status ON node_execution_logs(status);
CREATE INDEX IF NOT EXISTS idx_node_logs_pgvector_index_id
    ON node_execution_logs ((output->>'index_id'))
    WHERE module_type = 'pgvector_index_writer';
"""
    + AUDIT_SCHEMA_SQL
    + SOURCE_FILE_AUDIT_SQL
)


class DatabaseManager(
    SourceFileRepositoryMixin,
    WorkflowRunRepositoryMixin,
    SyncPostgresRepository,
):
    """PostgreSQL full ERD database manager."""

    def __init__(
        self,
        database_url: str = PGVECTOR_URL,
        *,
        ensure_schema: bool = True,
    ) -> None:
        super().__init__(database_url)

    def _raw_connection(self) -> Any:
        """Compatibility alias for legacy code inside this repository.

        New repositories use the public ``connection`` boundary inherited from
        ``SyncPostgresRepository``.
        """

        return self.connection()

    def _advisory_lock_connection(self) -> Any:
        """Open a dedicated session whose close guarantees advisory-lock release."""

        import psycopg2

        raw_url = getattr(self, "database_url", PGVECTOR_URL).replace(
            "postgresql+psycopg://", "postgresql://"
        )
        return psycopg2.connect(raw_url)

    def is_connected(self) -> bool:
        """Check whether a connection to the database can be established and used.

        Returns:
                bool: `True` if the database connection succeeds, `False` otherwise.
        """
        try:
            conn = self._raw_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1;")
                return True
            finally:
                conn.close()
        except Exception:
            return False

    async def is_connected_async(self) -> bool:
        """Check connectivity through the process-owned psycopg async pool."""
        try:
            async with get_pooled_async_connection(self.database_url) as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute("SELECT 1;")
                    await cursor.fetchone()
            return True
        except Exception:
            return False

    def ensure_schema(self) -> bool:
        """Create required database tables according to DDL_INIT.

        Returns:
            bool: True if schema initialization succeeded, False otherwise.
        """
        conn = None
        try:
            from backend.domains.benchmark.infrastructure.postgres import (
                BENCHMARK_SCHEMA_SQL,
            )
            from backend.domains.bi.infrastructure.postgres.database_schema import BI_SCHEMA_SQL

            conn = self._raw_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(DDL_INIT)
                    cur.execute(BI_SCHEMA_SQL)
                    cur.execute(BENCHMARK_SCHEMA_SQL)
                conn.commit()
                return True
            finally:
                conn.close()
        except Exception as err:
            logger.warning("PostgreSQL 스키마 초기화에 실패했습니다: %s", err, exc_info=True)
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
            return False


def main() -> None:
    """CLI entrypoint for initializing the current database schema."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Initialize the current database schema.")
    parser.parse_args()

    manager = DatabaseManager()
    exit_code = 0

    print("Ensuring database schema...")
    if manager.ensure_schema():
        print("Schema initialized.")
    else:
        print("Schema initialization failed.", file=sys.stderr)
        exit_code = 1

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
