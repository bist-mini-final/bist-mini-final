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
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Collection, Dict, Iterator, List, Optional
from uuid import uuid4

import psycopg2.extras

from backend.core.settings import PGVECTOR_URL

from .audit_schema import AUDIT_SCHEMA_SQL, SOURCE_FILE_AUDIT_SQL
from .connection_pool import get_pooled_async_connection, get_pooled_raw_connection

logger = logging.getLogger(__name__)


class WorkflowRunAlreadyClaimed(RuntimeError):
    """Raised when another database-connected worker owns the same run."""


class WorkflowLeaseLost(RuntimeError):
    """Raised when a worker tries to persist with an obsolete lease token."""


@dataclass(frozen=True)
class WorkflowRunLease:
    """A single claim generation shared by every worker persistence operation."""

    run_id: str
    token: str


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


class DatabaseManager:
    """PostgreSQL full ERD database manager."""

    def __init__(
        self,
        database_url: str = PGVECTOR_URL,
        *,
        ensure_schema: bool = True,
    ) -> None:
        self.database_url = database_url

    def _raw_connection(self) -> Any:
        raw_url = getattr(self, "database_url", PGVECTOR_URL).replace(
            "postgresql+psycopg://", "postgresql://"
        )
        return get_pooled_raw_connection(raw_url)

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

    @contextmanager
    def claim_workflow_run(
        self,
        run_id: str,
        *,
        queue_name: Optional[str] = None,
        worker_id: Optional[str] = None,
        lease_token: Optional[str] = None,
        stale_after_seconds: int = 180,
    ) -> Iterator[None]:
        """Hold a PostgreSQL advisory lock for one worker's run lifetime.

        The lock is released by PostgreSQL when the worker connection closes,
        including process or container crashes, so it prevents duplicate work
        without introducing a stale lease row.
        """

        conn = self._advisory_lock_connection()
        acquired = False
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT pg_try_advisory_lock(hashtextextended(%s, 0));",
                    (run_id,),
                )
                acquired = bool(cur.fetchone()[0])
            if not acquired:
                if worker_id is not None and lease_token is not None:
                    self.release_workflow_run_claim(
                        run_id,
                        worker_id,
                        lease_token,
                    )
                raise WorkflowRunAlreadyClaimed(
                    f"다른 배치 워커가 이미 실행을 소유하고 있습니다: {run_id}"
                )
            if queue_name is not None:
                if worker_id is None or lease_token is None:
                    raise ValueError("queue claim에는 worker_id와 lease_token이 필요합니다")
                if not self.finalize_workflow_run_claim(
                    run_id,
                    queue_name,
                    worker_id,
                    lease_token,
                    stale_after_seconds=stale_after_seconds,
                ):
                    raise WorkflowRunAlreadyClaimed(
                        f"작업 후보의 lease가 이미 변경되었습니다: {run_id}"
                    )
            yield
        finally:
            if acquired:
                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT pg_advisory_unlock(hashtextextended(%s, 0));",
                            (run_id,),
                        )
                except Exception:
                    logger.warning(
                        "워크플로 실행 advisory lock 해제 실패: %s",
                        run_id,
                        exc_info=True,
                    )
            try:
                conn.close()
            except Exception:
                pass

    def ensure_schema(self) -> bool:
        """Create required database tables according to DDL_INIT.

        Returns:
            bool: True if schema initialization succeeded, False otherwise.
        """
        conn = None
        try:
            from backend.features.benchmark.database_schema import (
                BENCHMARK_SCHEMA_SQL,
            )
            from backend.features.bi.database_schema import BI_SCHEMA_SQL

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

    def save_source_file(
        self,
        file_id: str,
        file_name: str,
        file_hash: str,
        file_type: str,
        file_size: int,
        storage_path: str,
        **_ignored: Any,
    ) -> None:
        """
        Insert a source file record or update the existing record with the same file ID.

        Parameters:
            file_id (str): Unique identifier for the source file.
            file_name (str): Name of the source file.
            file_hash (str): Content hash of the source file.
            file_type (str): Type of the source file.
            file_size (int): Size of the source file.
            storage_path (str): Path where the source file is stored.
        """
        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO source_files (file_id, file_name, file_hash, file_type, file_size, storage_path, is_deleted, deleted_at, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, FALSE, NULL, NOW())
                    ON CONFLICT (file_id) DO UPDATE SET
                        file_name = EXCLUDED.file_name,
                        file_hash = EXCLUDED.file_hash,
                        file_type = EXCLUDED.file_type,
                        file_size = EXCLUDED.file_size,
                        storage_path = EXCLUDED.storage_path,
                        is_deleted = FALSE,
                        deleted_at = NULL;
                    """,
                    (
                        file_id,
                        file_name,
                        file_hash,
                        file_type,
                        file_size,
                        storage_path,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    async def save_source_file_async(
        self,
        file_id: str,
        file_name: str,
        file_hash: str,
        file_type: str,
        file_size: int,
        storage_path: str,
        **_ignored: Any,
    ) -> None:
        """Persist upload metadata through native async PostgreSQL I/O."""
        async with get_pooled_async_connection(self.database_url) as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    INSERT INTO source_files (file_id, file_name, file_hash, file_type, file_size, storage_path, is_deleted, deleted_at, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, FALSE, NULL, NOW())
                    ON CONFLICT (file_id) DO UPDATE SET
                        file_name = EXCLUDED.file_name,
                        file_hash = EXCLUDED.file_hash,
                        file_type = EXCLUDED.file_type,
                        file_size = EXCLUDED.file_size,
                        storage_path = EXCLUDED.storage_path,
                        is_deleted = FALSE,
                        deleted_at = NULL;
                    """,
                    (
                        file_id,
                        file_name,
                        file_hash,
                        file_type,
                        file_size,
                        storage_path,
                    ),
                )
            await connection.commit()

    def delete_source_file(
        self,
        file_id_hash_or_name: str,
        *,
        actor_id: str = "system",
        request_id: str | None = None,
    ) -> bool:
        """Soft-delete source metadata by ID, hash, or unambiguous filename."""
        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                self._set_audit_context(cur, actor_id=actor_id, request_id=request_id)
                cur.execute(
                    """
                    UPDATE source_files
                    SET is_deleted = TRUE, deleted_at = NOW()
                    WHERE (file_id = %s OR file_hash = %s) AND is_deleted = FALSE;
                    """,
                    (file_id_hash_or_name, file_id_hash_or_name),
                )
                deleted = cur.rowcount > 0
                if not deleted:
                    safe_file_name = Path(file_id_hash_or_name).name
                    cur.execute(
                        """
                        SELECT file_id
                        FROM source_files
                        WHERE file_name = %s AND is_deleted = FALSE
                        ORDER BY created_at DESC
                        LIMIT 2;
                        """,
                        (safe_file_name,),
                    )
                    matches = cur.fetchmany(2)
                    if len(matches) > 1:
                        raise ValueError(
                            "동일한 파일명의 source_files 레코드가 여러 개입니다. "
                            "file_id 또는 file_hash로 삭제하세요"
                        )
                    if matches:
                        cur.execute(
                            "UPDATE source_files SET is_deleted = TRUE, "
                            "deleted_at = NOW() WHERE file_id = %s "
                            "AND is_deleted = FALSE;",
                            (matches[0][0],),
                        )
                        deleted = cur.rowcount > 0
            conn.commit()
            return deleted
        finally:
            conn.close()

    @staticmethod
    def _set_audit_context(
        cursor: Any,
        *,
        actor_id: str,
        request_id: str | None,
    ) -> None:
        cursor.execute(
            "SELECT set_config('app.audit_actor_id', %s, TRUE), "
            "set_config('app.audit_request_id', %s, TRUE)",
            (actor_id[:128], (request_id or "")[:128]),
        )

    def save_sheets(self, file_id: str, sheets_info: List[Dict[str, Any]]) -> None:
        """Insert or replace sheet records for a source file."""
        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                for s in sheets_info:
                    sheet_name = s.get("sheet_name", "Sheet1")
                    sheet_id = f"{file_id}:{sheet_name}"
                    cur.execute(
                        """
                        INSERT INTO sheets (sheet_id, file_id, sheet_name, sheet_index, is_visible, row_count, column_count, detected_tables, parsed_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (sheet_id) DO UPDATE SET
                            sheet_index = EXCLUDED.sheet_index,
                            is_visible = EXCLUDED.is_visible,
                            row_count = EXCLUDED.row_count,
                            column_count = EXCLUDED.column_count,
                            detected_tables = EXCLUDED.detected_tables,
                            parsed_at = NOW();
                        """,
                        (
                            sheet_id,
                            file_id,
                            sheet_name,
                            s.get("sheet_index", 0),
                            s.get("is_visible", True),
                            s.get("row_count", 0),
                            s.get("column_count", 0),
                            psycopg2.extras.Json(s.get("detected_tables", [])),
                        ),
                    )
            conn.commit()
        finally:
            conn.close()

    def list_sheets(self, file_id: str) -> List[Dict[str, Any]]:
        """Return normalized sheet metadata for one workbook in display order."""

        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT sheet_name, sheet_index, is_visible, row_count,
                           column_count, detected_tables, parsed_at
                    FROM sheets
                    WHERE file_id = %s
                    ORDER BY sheet_index, sheet_name;
                    """,
                    (file_id,),
                )
                return [
                    {
                        "sheet_name": str(row[0]),
                        "sheet_index": int(row[1]),
                        "is_visible": bool(row[2]),
                        "row_count": int(row[3]),
                        "column_count": int(row[4]),
                        "detected_tables": row[5] or [],
                        "parsed_at": (
                            row[6].isoformat() if hasattr(row[6], "isoformat") else str(row[6])
                        ),
                    }
                    for row in cur.fetchall()
                ]
        finally:
            conn.close()

    def save_workflow_run(
        self,
        run_dict_or_model: Any,
        *,
        lease_token: Optional[str] = None,
    ) -> None:
        """Insert or update a workflow run and its node execution logs."""
        if hasattr(run_dict_or_model, "model_dump"):
            data = run_dict_or_model.model_dump(mode="json")
        else:
            data = dict(run_dict_or_model)

        run_id = data.get("id") or data.get("run_id")
        if not run_id:
            raise ValueError("run_id is required to save workflow run")

        workflow_id = data.get("workflow_id", "")
        workflow_updated_at = data.get("workflow_updated_at", "")
        status = data.get("status", "queued")
        schema_version = data.get("schema_version", 2)
        graph = data.get("graph", {})
        runtime_inputs = data.get("runtime_inputs", {})
        use_cache = bool(data.get("use_cache", True))
        orchestration = data.get("orchestration", {})
        batches = data.get("batches", [])
        nodes = data.get("nodes", {})
        created_at = data.get("created_at") or datetime.now(timezone.utc).isoformat()
        updated_at = data.get("updated_at") or datetime.now(timezone.utc).isoformat()

        failed_state = next(
            (st for st in nodes.values() if isinstance(st, dict) and st.get("status") == "failed"),
            None,
        )
        error_message = failed_state.get("error") if failed_state else None

        completed_at = None
        if status in ("completed", "failed"):
            completed_at = updated_at

        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                if lease_token is not None:
                    cur.execute(
                        """
                        SELECT 1
                        FROM workflow_runs
                        WHERE run_id = %s AND lease_token = %s
                        FOR UPDATE;
                        """,
                        (run_id, lease_token),
                    )
                    if cur.fetchone() is None:
                        raise WorkflowLeaseLost(f"워크플로 lease 소유권을 잃었습니다: {run_id}")
                cur.execute(
                    """
                    INSERT INTO workflow_runs (
                        run_id, workflow_id, workflow_updated_at, status, schema_version,
                        graph, runtime_inputs, use_cache, orchestration, batches, nodes,
                        error_message, created_at, updated_at, completed_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (run_id) DO UPDATE SET
                        workflow_id = EXCLUDED.workflow_id,
                        workflow_updated_at = EXCLUDED.workflow_updated_at,
                        status = CASE
                            WHEN workflow_runs.cancel_requested
                                 AND EXCLUDED.status IN ('queued', 'running')
                            THEN 'paused'
                            ELSE EXCLUDED.status
                        END,
                        schema_version = EXCLUDED.schema_version,
                        graph = EXCLUDED.graph,
                        runtime_inputs = EXCLUDED.runtime_inputs,
                        use_cache = EXCLUDED.use_cache,
                        orchestration = EXCLUDED.orchestration,
                        batches = EXCLUDED.batches,
                        nodes = EXCLUDED.nodes,
                        error_message = EXCLUDED.error_message,
                        updated_at = EXCLUDED.updated_at,
                        completed_at = EXCLUDED.completed_at;
                    """,
                    (
                        run_id,
                        workflow_id,
                        workflow_updated_at,
                        status,
                        schema_version,
                        psycopg2.extras.Json(graph),
                        psycopg2.extras.Json(runtime_inputs),
                        use_cache,
                        psycopg2.extras.Json(orchestration),
                        psycopg2.extras.Json(batches),
                        psycopg2.extras.Json(nodes),
                        error_message,
                        created_at,
                        updated_at,
                        completed_at,
                    ),
                )

                for node_id, node_state in nodes.items():
                    if not isinstance(node_state, dict):
                        continue
                    log_id = f"{run_id}:{node_id}"
                    module_type = node_state.get("module_type", "")
                    node_status = node_state.get("status", "pending")
                    input_payload = node_state.get("input_payload")
                    config_payload = node_state.get("config_payload") or {}
                    output = node_state.get("output")
                    error = node_state.get("error")
                    cache_hit = bool(node_state.get("cache_hit", False))
                    outcome = node_state.get("outcome")
                    progress = node_state.get("progress") or {}
                    batch_index = node_state.get("batch_index", 0)
                    elapsed_ms = node_state.get("elapsed_ms")
                    cost_usd = node_state.get("cost_usd")
                    usage = node_state.get("usage")
                    started_at = node_state.get("started_at")
                    node_completed_at = node_state.get("completed_at")

                    cur.execute(
                        """
                        INSERT INTO node_execution_logs (
                            log_id, run_id, node_id, module_type, batch_index,
                            status, input_payload, config_payload, output, error,
                            cache_hit, outcome, progress, elapsed_ms, cost_usd,
                            usage, started_at, completed_at, created_at
                        )
                        VALUES (
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, NOW()
                        )
                        ON CONFLICT (log_id) DO UPDATE SET
                            module_type = EXCLUDED.module_type,
                            batch_index = EXCLUDED.batch_index,
                            status = EXCLUDED.status,
                            input_payload = EXCLUDED.input_payload,
                            config_payload = EXCLUDED.config_payload,
                            output = EXCLUDED.output,
                            error = EXCLUDED.error,
                            cache_hit = EXCLUDED.cache_hit,
                            outcome = EXCLUDED.outcome,
                            progress = EXCLUDED.progress,
                            elapsed_ms = EXCLUDED.elapsed_ms,
                            cost_usd = EXCLUDED.cost_usd,
                            usage = EXCLUDED.usage,
                            started_at = EXCLUDED.started_at,
                            completed_at = EXCLUDED.completed_at;
                        """,
                        (
                            log_id,
                            run_id,
                            node_id,
                            module_type,
                            batch_index,
                            node_status,
                            psycopg2.extras.Json(input_payload)
                            if input_payload is not None
                            else None,
                            psycopg2.extras.Json(config_payload),
                            psycopg2.extras.Json(output) if output is not None else None,
                            error,
                            cache_hit,
                            outcome,
                            psycopg2.extras.Json(progress),
                            elapsed_ms,
                            cost_usd,
                            psycopg2.extras.Json(usage) if usage is not None else None,
                            started_at,
                            node_completed_at,
                        ),
                    )
            conn.commit()
        finally:
            conn.close()

    def get_workflow_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Load a full workflow run from database by run_id."""
        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT run_id, workflow_id, workflow_updated_at, status, schema_version,
                           graph, runtime_inputs, use_cache, orchestration, batches, nodes,
                           created_at, updated_at
                    FROM workflow_runs
                    WHERE run_id = %s;
                    """,
                    (run_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                data = {
                    "id": row[0],
                    "workflow_id": row[1],
                    "workflow_updated_at": row[2] or "",
                    "status": row[3],
                    "schema_version": row[4],
                    "graph": row[5] or {},
                    "runtime_inputs": row[6] or {},
                    "use_cache": bool(row[7]),
                    "orchestration": row[8] or {},
                    "batches": row[9] or [],
                    "nodes": row[10] or {},
                    "created_at": row[11].isoformat()
                    if hasattr(row[11], "isoformat")
                    else str(row[11]),
                    "updated_at": row[12].isoformat()
                    if hasattr(row[12], "isoformat")
                    else str(row[12]),
                }
                cur.execute(
                    """
                    SELECT node_id, module_type, batch_index, status,
                           input_payload, config_payload, output, error,
                           cache_hit, outcome, progress, elapsed_ms, cost_usd,
                           usage, started_at, completed_at
                    FROM node_execution_logs
                    WHERE run_id = %s
                    ORDER BY batch_index ASC, created_at ASC;
                    """,
                    (run_id,),
                )
                node_rows = cur.fetchall()
                if node_rows:
                    persisted_nodes = data["nodes"]
                    data["nodes"] = {
                        str(node_row[0]): {
                            **(
                                persisted_nodes.get(str(node_row[0]), {})
                                if isinstance(persisted_nodes, dict)
                                else {}
                            ),
                            "node_id": node_row[0],
                            "module_type": node_row[1],
                            "batch_index": node_row[2] or 0,
                            "status": node_row[3],
                            "input_payload": node_row[4],
                            "config_payload": node_row[5] or {},
                            "output": node_row[6],
                            "error": node_row[7],
                            "cache_hit": bool(node_row[8]),
                            "outcome": node_row[9],
                            "progress": node_row[10] or {},
                            "elapsed_ms": node_row[11],
                            "cost_usd": node_row[12],
                            "usage": node_row[13],
                            "started_at": (
                                node_row[14].isoformat()
                                if hasattr(node_row[14], "isoformat")
                                else str(node_row[14])
                                if node_row[14]
                                else None
                            ),
                            "completed_at": (
                                node_row[15].isoformat()
                                if hasattr(node_row[15], "isoformat")
                                else str(node_row[15])
                                if node_row[15]
                                else None
                            ),
                        }
                        for node_row in node_rows
                    }
                return data
        finally:
            conn.close()

    @staticmethod
    def _workflow_run_summary_from_row(
        row: Any,
        nodes: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Build a product-facing run snapshot without loading large node payloads."""

        status = row[3]
        node_statuses = {str(node.get("status")) for node in nodes.values() if node.get("status")}
        if status in ("queued", "running") and node_statuses:
            if node_statuses <= {"succeeded", "skipped"}:
                status = "completed"
            elif "failed" in node_statuses:
                status = "failed"
        return {
            "id": row[0],
            "workflow_id": row[1],
            "workflow_updated_at": row[2] or "",
            "status": status,
            "schema_version": row[4],
            "graph": row[5] or {},
            "runtime_inputs": row[6] or {},
            "use_cache": bool(row[7]),
            "orchestration": row[8] or {},
            "batches": row[9] or [],
            "nodes": nodes,
            "created_at": (row[10].isoformat() if hasattr(row[10], "isoformat") else str(row[10])),
            "updated_at": (row[11].isoformat() if hasattr(row[11], "isoformat") else str(row[11])),
        }

    @staticmethod
    def _node_summary_from_row(row: Any) -> Dict[str, Any]:
        """Convert a lightweight node_execution_logs projection to RunNodeState."""

        return {
            "node_id": row[1],
            "module_type": row[2],
            "batch_index": row[3] or 0,
            "status": row[4],
            "input_payload": None,
            "config_payload": row[5] or {},
            "output": row[6],
            "error": row[7],
            "cache_key": None,
            "cache_hit": bool(row[8]),
            "outcome": row[9],
            "skip_reason": None,
            "progress": row[10] or {},
            "elapsed_ms": row[11],
            "cost_usd": row[12],
            "usage": row[13],
            "started_at": (
                row[14].isoformat()
                if hasattr(row[14], "isoformat")
                else str(row[14])
                if row[14]
                else None
            ),
            "completed_at": (
                row[15].isoformat()
                if hasattr(row[15], "isoformat")
                else str(row[15])
                if row[15]
                else None
            ),
        }

    def _get_workflow_node_summaries(
        self,
        conn: Any,
        run_ids: List[str],
    ) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Load statuses and compact result metadata, never document/vector arrays."""

        if not run_ids:
            return {}
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT run_id, node_id, module_type, batch_index, status,
                       config_payload,
                       CASE
                           WHEN module_type IN (
                               'processed_file_selector',
                               'luna_vlm_structure_detector',
                               'pgvector_index_writer',
                               'company_entity_extractor',
                               'sheet_metadata_persistence',
                               'query_input',
                               'llm_query_router',
                               'decomposer',
                               'reader'
                           ) THEN output
                           ELSE NULL
                       END AS projected_output,
                       error, cache_hit, outcome, progress, elapsed_ms,
                       cost_usd, usage, started_at, completed_at
                FROM node_execution_logs
                WHERE run_id = ANY(%s)
                ORDER BY run_id, batch_index ASC, created_at ASC;
                """,
                (run_ids,),
            )
            summaries: Dict[str, Dict[str, Dict[str, Any]]] = {run_id: {} for run_id in run_ids}
            for row in cur.fetchall():
                run_id = str(row[0])
                node = self._node_summary_from_row(row)
                summaries.setdefault(run_id, {})[node["node_id"]] = node
            return summaries

    def get_workflow_run_summary(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Load a polling-safe run snapshot without large node inputs or outputs."""

        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT run_id, workflow_id, workflow_updated_at, status,
                           schema_version, graph, runtime_inputs, use_cache,
                           orchestration, batches, created_at, updated_at
                    FROM workflow_runs
                    WHERE run_id = %s;
                    """,
                    (run_id,),
                )
                row = cur.fetchone()
            if not row:
                return None
            nodes_by_run = self._get_workflow_node_summaries(conn, [run_id])
            return self._workflow_run_summary_from_row(
                row,
                nodes_by_run.get(run_id, {}),
            )
        finally:
            conn.close()

    def list_workflow_run_summaries(
        self,
        workflow_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """List polling-safe run snapshots ordered by most recent update."""

        if limit is not None and limit < 1:
            raise ValueError("limit must be at least 1")

        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                query = """
                    SELECT run_id, workflow_id, workflow_updated_at, status,
                           schema_version, graph, runtime_inputs, use_cache,
                           orchestration, batches, created_at, updated_at
                    FROM workflow_runs
                """
                if workflow_id is not None:
                    query += " WHERE workflow_id = %s ORDER BY updated_at DESC"
                    parameters: tuple[object, ...] = (workflow_id,)
                else:
                    query += " ORDER BY updated_at DESC"
                    parameters = ()
                if limit is not None:
                    query += " LIMIT %s"
                    parameters = (*parameters, limit)
                cur.execute(query + ";", parameters)
                rows = cur.fetchall()
            run_ids = [str(row[0]) for row in rows]
            nodes_by_run = self._get_workflow_node_summaries(conn, run_ids)
            return [
                self._workflow_run_summary_from_row(
                    row,
                    nodes_by_run.get(str(row[0]), {}),
                )
                for row in rows
            ]
        finally:
            conn.close()

    def find_ingestion_run_id_by_index(self, index_id: str) -> Optional[str]:
        """Resolve an index to its durable ingestion run without scanning run JSON."""

        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT log.run_id
                    FROM node_execution_logs AS log
                    JOIN workflow_runs AS run ON run.run_id = log.run_id
                    WHERE run.workflow_id = 'excel_ingestion'
                      AND log.module_type = 'pgvector_index_writer'
                      AND (
                          log.output->>'index_id' = %s
                          OR log.progress->>'target_index_id' = %s
                      )
                    ORDER BY log.completed_at DESC NULLS LAST,
                             run.updated_at DESC
                    LIMIT 1;
                    """,
                    (index_id, index_id),
                )
                row = cur.fetchone()
                return str(row[0]) if row else None
        finally:
            conn.close()

    def save_workflow_node_progress(
        self,
        run: Any,
        node_id: str,
        *,
        lease_token: Optional[str] = None,
    ) -> None:
        """Persist one node's live status without retransmitting the full run JSON."""

        if hasattr(run, "model_dump"):
            run_id = getattr(run, "id", None)
            run_status = getattr(run, "status", "running")
            updated_at = getattr(run, "updated_at", None)
            batches = [
                batch.model_dump(mode="json") if hasattr(batch, "model_dump") else dict(batch)
                for batch in getattr(run, "batches", [])
            ]
            raw_node = getattr(run, "nodes", {}).get(node_id)
            node_state = (
                raw_node.model_dump(mode="json")
                if raw_node is not None and hasattr(raw_node, "model_dump")
                else dict(raw_node)
                if raw_node is not None
                else None
            )
        else:
            data = dict(run)
            run_id = data.get("id") or data.get("run_id")
            run_status = data.get("status", "running")
            updated_at = data.get("updated_at")
            batches = data.get("batches") or []
            node_state = (data.get("nodes") or {}).get(node_id)
        if not isinstance(node_state, dict):
            raise ValueError(f"run에 progress 대상 노드가 없습니다: {node_id}")
        if not run_id:
            raise ValueError("run_id is required to save workflow progress")

        updated_at = updated_at or datetime.now(timezone.utc).isoformat()
        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE workflow_runs
                    SET status = CASE
                            WHEN cancel_requested AND %s IN ('queued', 'running')
                            THEN 'paused'
                            ELSE %s
                        END,
                        batches = %s,
                        updated_at = %s,
                        heartbeat_at = CASE
                            WHEN worker_id IS NOT NULL THEN NOW()
                            ELSE heartbeat_at
                        END
                    WHERE run_id = %s
                      AND lease_token IS NOT DISTINCT FROM %s;
                    """,
                    (
                        run_status,
                        run_status,
                        psycopg2.extras.Json(batches),
                        updated_at,
                        run_id,
                        lease_token,
                    ),
                )
                if cur.rowcount != 1:
                    raise WorkflowLeaseLost(f"워크플로 lease 소유권을 잃었습니다: {run_id}")
                cur.execute(
                    """
                    INSERT INTO node_execution_logs (
                        log_id, run_id, node_id, module_type, batch_index,
                        status, config_payload, error, cache_hit, outcome,
                        progress, elapsed_ms, cost_usd, usage, started_at,
                        completed_at, created_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, NOW()
                    )
                    ON CONFLICT (log_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        config_payload = EXCLUDED.config_payload,
                        error = EXCLUDED.error,
                        cache_hit = EXCLUDED.cache_hit,
                        outcome = EXCLUDED.outcome,
                        progress = EXCLUDED.progress,
                        elapsed_ms = EXCLUDED.elapsed_ms,
                        cost_usd = EXCLUDED.cost_usd,
                        usage = EXCLUDED.usage,
                        started_at = EXCLUDED.started_at,
                        completed_at = EXCLUDED.completed_at;
                    """,
                    (
                        f"{run_id}:{node_id}",
                        run_id,
                        node_id,
                        node_state.get("module_type", ""),
                        node_state.get("batch_index", 0),
                        node_state.get("status", "pending"),
                        psycopg2.extras.Json(node_state.get("config_payload") or {}),
                        node_state.get("error"),
                        bool(node_state.get("cache_hit", False)),
                        node_state.get("outcome"),
                        psycopg2.extras.Json(node_state.get("progress") or {}),
                        node_state.get("elapsed_ms"),
                        node_state.get("cost_usd"),
                        psycopg2.extras.Json(node_state.get("usage"))
                        if node_state.get("usage") is not None
                        else None,
                        node_state.get("started_at"),
                        node_state.get("completed_at"),
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def save_workflow_node_state(
        self,
        run: Any,
        node_id: str,
        *,
        lease_token: Optional[str] = None,
    ) -> None:
        """Upsert one completed node and run metadata without rewriting the DAG."""

        run_id = getattr(run, "id", None)
        node = getattr(run, "nodes", {}).get(node_id)
        if not run_id or node is None:
            raise ValueError(f"run에 저장할 노드가 없습니다: {node_id}")
        node_state = node.model_dump(mode="json") if hasattr(node, "model_dump") else dict(node)
        batches = [
            batch.model_dump(mode="json") if hasattr(batch, "model_dump") else dict(batch)
            for batch in getattr(run, "batches", [])
        ]
        updated_at = getattr(run, "updated_at", None) or datetime.now(timezone.utc).isoformat()
        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE workflow_runs
                    SET status = CASE
                            WHEN cancel_requested AND %s IN ('queued', 'running')
                            THEN 'paused'
                            ELSE %s
                        END,
                        batches = %s,
                        error_message = %s,
                        updated_at = %s,
                        completed_at = CASE
                            WHEN %s IN ('completed', 'failed')
                            THEN %s::timestamptz
                            ELSE NULL::timestamptz
                        END,
                        heartbeat_at = NOW()
                    WHERE run_id = %s
                      AND lease_token IS NOT DISTINCT FROM %s;
                    """,
                    (
                        run.status,
                        run.status,
                        psycopg2.extras.Json(batches),
                        node_state.get("error") if node_state.get("status") == "failed" else None,
                        updated_at,
                        run.status,
                        updated_at,
                        run_id,
                        lease_token,
                    ),
                )
                if cur.rowcount != 1:
                    raise WorkflowLeaseLost(f"워크플로 lease 소유권을 잃었습니다: {run_id}")
                cur.execute(
                    """
                    INSERT INTO node_execution_logs (
                        log_id, run_id, node_id, module_type, batch_index,
                        status, input_payload, config_payload, output, error,
                        cache_hit, outcome, progress, elapsed_ms, cost_usd,
                        usage, started_at, completed_at, created_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, NOW()
                    )
                    ON CONFLICT (log_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        input_payload = EXCLUDED.input_payload,
                        config_payload = EXCLUDED.config_payload,
                        output = EXCLUDED.output,
                        error = EXCLUDED.error,
                        cache_hit = EXCLUDED.cache_hit,
                        outcome = EXCLUDED.outcome,
                        progress = EXCLUDED.progress,
                        elapsed_ms = EXCLUDED.elapsed_ms,
                        cost_usd = EXCLUDED.cost_usd,
                        usage = EXCLUDED.usage,
                        started_at = EXCLUDED.started_at,
                        completed_at = EXCLUDED.completed_at;
                    """,
                    (
                        f"{run_id}:{node_id}",
                        run_id,
                        node_id,
                        node_state.get("module_type", ""),
                        node_state.get("batch_index", 0),
                        node_state.get("status", "pending"),
                        psycopg2.extras.Json(node_state.get("input_payload"))
                        if node_state.get("input_payload") is not None
                        else None,
                        psycopg2.extras.Json(node_state.get("config_payload") or {}),
                        psycopg2.extras.Json(node_state.get("output"))
                        if node_state.get("output") is not None
                        else None,
                        node_state.get("error"),
                        bool(node_state.get("cache_hit", False)),
                        node_state.get("outcome"),
                        psycopg2.extras.Json(node_state.get("progress") or {}),
                        node_state.get("elapsed_ms"),
                        node_state.get("cost_usd"),
                        psycopg2.extras.Json(node_state.get("usage"))
                        if node_state.get("usage") is not None
                        else None,
                        node_state.get("started_at"),
                        node_state.get("completed_at"),
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def enqueue_workflow_run(
        self,
        run_id: str,
        queue_name: str,
        *,
        submission_attempt: int,
        submitted_at: str,
        priority: int = 0,
    ) -> bool:
        """Place one persisted run on the durable Kubernetes work queue."""

        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE workflow_runs
                    SET status = 'queued',
                        queue_name = %s,
                        worker_id = NULL,
                        lease_token = NULL,
                        priority = %s,
                        available_at = NOW(),
                        claimed_at = NULL,
                        heartbeat_at = NULL,
                        orchestration = jsonb_build_object(
                            'backend', 'kubernetes',
                            'deployment_name', %s::text,
                            'external_run_id', NULL,
                            'submission_attempt', %s::int,
                            'submitted_at', %s::text
                        ),
                        updated_at = NOW(),
                        completed_at = NULL
                    WHERE run_id = %s
                      AND cancel_requested = FALSE;
                    """,
                    (
                        queue_name,
                        priority,
                        queue_name,
                        submission_attempt,
                        submitted_at,
                        run_id,
                    ),
                )
                enqueued = cur.rowcount == 1
                if not enqueued:
                    cur.execute(
                        "SELECT cancel_requested FROM workflow_runs WHERE run_id = %s;",
                        (run_id,),
                    )
                    row = cur.fetchone()
                    if row is None:
                        raise FileNotFoundError(run_id)
            conn.commit()
            return enqueued
        finally:
            conn.close()

    def claim_next_workflow_run(
        self,
        queue_name: str,
        worker_id: str,
        *,
        stale_after_seconds: int = 180,
        excluded_run_ids: Collection[str] = (),
    ) -> Optional[WorkflowRunLease]:
        """Select one claim candidate with ``FOR UPDATE SKIP LOCKED``.

        The returned token is not persisted here. The caller must acquire the
        run's advisory lock and pass this same generation to
        :meth:`claim_workflow_run`, which then finalizes the lease. This keeps
        a stale but still-running advisory-lock owner from being overwritten.
        """

        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT run_id
                    FROM workflow_runs
                    WHERE queue_name = %s
                      AND NOT (run_id = ANY(%s::varchar[]))
                      AND cancel_requested = FALSE
                      AND (
                          (status = 'queued' AND available_at <= NOW())
                          OR (
                              status = 'running'
                              AND (
                                  worker_id = %s
                                  OR heartbeat_at IS NULL
                                  OR heartbeat_at < NOW() - (%s * INTERVAL '1 second')
                              )
                          )
                      )
                    ORDER BY
                        CASE WHEN worker_id = %s THEN 0 ELSE 1 END,
                        priority DESC,
                        available_at ASC,
                        created_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED;
                    """,
                    (
                        queue_name,
                        list(excluded_run_ids),
                        worker_id,
                        stale_after_seconds,
                        worker_id,
                    ),
                )
                row = cur.fetchone()
            conn.commit()
            return WorkflowRunLease(str(row[0]), uuid4().hex) if row else None
        finally:
            conn.close()

    def finalize_workflow_run_claim(
        self,
        run_id: str,
        queue_name: str,
        worker_id: str,
        lease_token: str,
        *,
        stale_after_seconds: int = 180,
    ) -> bool:
        """Finalize a candidate only after its advisory lock is held."""

        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE workflow_runs
                    SET status = 'running',
                        worker_id = %s,
                        lease_token = %s,
                        claimed_at = NOW(),
                        heartbeat_at = NOW(),
                        attempt_count = attempt_count + 1,
                        orchestration = jsonb_set(
                            jsonb_set(
                                orchestration,
                                '{backend}',
                                to_jsonb('kubernetes'::text)
                            ),
                            '{external_run_id}',
                            to_jsonb(%s::text)
                        ),
                        updated_at = NOW()
                    WHERE run_id = %s
                      AND queue_name = %s
                      AND cancel_requested = FALSE
                      AND (
                          (status = 'queued' AND available_at <= NOW())
                          OR (
                              status = 'running'
                              AND (
                                  worker_id = %s
                                  OR heartbeat_at IS NULL
                                  OR heartbeat_at < NOW() - (%s * INTERVAL '1 second')
                              )
                          )
                      );
                    """,
                    (
                        worker_id,
                        lease_token,
                        worker_id,
                        run_id,
                        queue_name,
                        worker_id,
                        stale_after_seconds,
                    ),
                )
                finalized = cur.rowcount == 1
            conn.commit()
            return finalized
        finally:
            conn.close()

    def release_workflow_run_claim(
        self,
        run_id: str,
        worker_id: str,
        lease_token: str,
    ) -> bool:
        """Conditionally roll back only the caller's unowned lease generation."""

        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE workflow_runs
                    SET status = 'queued',
                        worker_id = NULL,
                        lease_token = NULL,
                        claimed_at = NULL,
                        heartbeat_at = NULL,
                        available_at = NOW(),
                        orchestration = jsonb_set(
                            orchestration,
                            '{external_run_id}',
                            'null'::jsonb
                        ),
                        updated_at = NOW()
                    WHERE run_id = %s
                      AND worker_id = %s
                      AND lease_token = %s
                      AND status = 'running';
                    """,
                    (run_id, worker_id, lease_token),
                )
                released = cur.rowcount == 1
            conn.commit()
            return released
        finally:
            conn.close()

    def heartbeat_workflow_run(
        self,
        run_id: str,
        worker_id: str,
        lease_token: str,
    ) -> bool:
        """Renew the lease only while the caller still owns a running item."""

        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE workflow_runs
                    SET heartbeat_at = NOW(), updated_at = NOW()
                    WHERE run_id = %s
                      AND worker_id = %s
                      AND lease_token = %s
                      AND status = 'running'
                      AND cancel_requested = FALSE;
                    """,
                    (run_id, worker_id, lease_token),
                )
                renewed = cur.rowcount == 1
            conn.commit()
            return renewed
        finally:
            conn.close()

    def fail_workflow_run_claim(
        self,
        run_id: str,
        worker_id: str,
        lease_token: str,
        error_message: str,
    ) -> bool:
        """Make a fatal worker/bootstrap error terminal for its owned run."""

        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE workflow_runs
                    SET status = 'failed',
                        error_message = %s,
                        updated_at = NOW(),
                        completed_at = NOW()
                    WHERE run_id = %s
                      AND worker_id = %s
                      AND lease_token = %s
                      AND status = 'running';
                    """,
                    (error_message[:2000], run_id, worker_id, lease_token),
                )
                failed = cur.rowcount == 1
            conn.commit()
            return failed
        finally:
            conn.close()

    def request_workflow_cancel(self, run_id: str) -> bool:
        """Persist a cross-process cancellation request for an active queue item."""

        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE workflow_runs
                    SET cancel_requested = TRUE,
                        status = CASE
                            WHEN status IN ('queued', 'running') THEN 'paused'
                            ELSE status
                        END,
                        updated_at = NOW()
                    WHERE run_id = %s;
                    """,
                    (run_id,),
                )
                requested = cur.rowcount == 1
            conn.commit()
            return requested
        finally:
            conn.close()

    def is_workflow_cancel_requested(self, run_id: str) -> bool:
        """Return whether an API process asked the external worker to stop."""

        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT cancel_requested FROM workflow_runs WHERE run_id = %s;",
                    (run_id,),
                )
                row = cur.fetchone()
                return bool(row and row[0])
        finally:
            conn.close()

    def clear_workflow_cancel_request(self, run_id: str) -> bool:
        """Allow an explicitly resumed run to be enqueued again."""

        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE workflow_runs
                    SET cancel_requested = FALSE,
                        updated_at = NOW()
                    WHERE run_id = %s;
                    """,
                    (run_id,),
                )
                changed = cur.rowcount == 1
            conn.commit()
            return changed
        finally:
            conn.close()

    def queue_depth(
        self,
        queue_name: str,
        *,
        stale_after_seconds: int = 180,
    ) -> int:
        """Return the same claimable count used by the KEDA PostgreSQL scaler."""

        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM workflow_runs
                    WHERE queue_name = %s
                      AND cancel_requested = FALSE
                      AND (
                          (status = 'queued' AND available_at <= NOW())
                          OR (
                              status = 'running'
                              AND (
                                  heartbeat_at IS NULL
                                  OR heartbeat_at < NOW() - (%s * INTERVAL '1 second')
                              )
                          )
                      );
                    """,
                    (queue_name, stale_after_seconds),
                )
                row = cur.fetchone()
                return int(row[0]) if row else 0
        finally:
            conn.close()

    def list_active_workflow_leases(
        self,
        *,
        stale_after_seconds: int = 180,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Return bounded read-only queue/lease data for the operations portal."""
        safe_limit = max(1, min(limit, 500))
        conn = self._raw_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        run_id,
                        workflow_id,
                        queue_name,
                        status,
                        worker_id,
                        priority,
                        attempt_count,
                        available_at,
                        claimed_at,
                        heartbeat_at,
                        cancel_requested,
                        created_at,
                        updated_at,
                        CASE WHEN heartbeat_at IS NULL THEN NULL ELSE
                            GREATEST(0, EXTRACT(EPOCH FROM (NOW() - heartbeat_at)))
                        END AS heartbeat_age_seconds,
                        CASE WHEN status <> 'running' OR heartbeat_at IS NULL THEN NULL ELSE
                            GREATEST(
                                0,
                                %s - EXTRACT(EPOCH FROM (NOW() - heartbeat_at))
                            )
                        END AS lease_ttl_seconds,
                        CASE WHEN status = 'running' THEN (
                            heartbeat_at IS NULL OR
                            heartbeat_at < NOW() - (%s * INTERVAL '1 second')
                        ) ELSE FALSE END AS lease_stale
                    FROM workflow_runs
                    WHERE queue_name IS NOT NULL
                      AND status IN ('queued', 'running', 'paused')
                    ORDER BY
                        CASE status WHEN 'running' THEN 0 WHEN 'queued' THEN 1 ELSE 2 END,
                        priority DESC,
                        updated_at DESC
                    LIMIT %s
                    """,
                    (stale_after_seconds, stale_after_seconds, safe_limit),
                )
                return [dict(row) for row in cur.fetchall()]
        finally:
            conn.close()

    def list_workflow_runs(self, workflow_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List workflow runs from database, ordered by most recently updated."""
        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                if workflow_id is not None:
                    cur.execute(
                        """
                        SELECT run_id, workflow_id, workflow_updated_at, status, schema_version,
                               graph, runtime_inputs, use_cache, orchestration, batches, nodes,
                               created_at, updated_at
                        FROM workflow_runs
                        WHERE workflow_id = %s
                        ORDER BY updated_at DESC;
                        """,
                        (workflow_id,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT run_id, workflow_id, workflow_updated_at, status, schema_version,
                               graph, runtime_inputs, use_cache, orchestration, batches, nodes,
                               created_at, updated_at
                        FROM workflow_runs
                        ORDER BY updated_at DESC;
                        """
                    )
                rows = cur.fetchall()
                runs = []
                for row in rows:
                    runs.append(
                        {
                            "id": row[0],
                            "workflow_id": row[1],
                            "workflow_updated_at": row[2] or "",
                            "status": row[3],
                            "schema_version": row[4],
                            "graph": row[5] or {},
                            "runtime_inputs": row[6] or {},
                            "use_cache": bool(row[7]),
                            "orchestration": row[8] or {},
                            "batches": row[9] or [],
                            "nodes": row[10] or {},
                            "created_at": row[11].isoformat()
                            if hasattr(row[11], "isoformat")
                            else str(row[11]),
                            "updated_at": row[12].isoformat()
                            if hasattr(row[12], "isoformat")
                            else str(row[12]),
                        }
                    )
                return runs
        finally:
            conn.close()

    def list_pending_workflow_run_ids(
        self,
        workflow_ids: Optional[List[str]] = None,
    ) -> List[str]:
        """Return only IDs needed for startup recovery without loading node payloads."""

        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                if workflow_ids is None:
                    cur.execute(
                        """
                        SELECT run_id
                        FROM workflow_runs
                        WHERE status IN ('queued', 'running')
                        ORDER BY created_at ASC;
                        """
                    )
                else:
                    cur.execute(
                        """
                        SELECT run_id
                        FROM workflow_runs
                        WHERE status IN ('queued', 'running')
                          AND workflow_id = ANY(%s)
                        ORDER BY created_at ASC;
                        """,
                        (workflow_ids,),
                    )
                return [str(row[0]) for row in cur.fetchall()]
        finally:
            conn.close()

    def list_pending_workflow_run_references(
        self,
        workflow_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Return lightweight recovery metadata without graph or node JSONB."""

        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                if workflow_ids is None:
                    cur.execute(
                        """
                        SELECT run_id, workflow_id, status, orchestration
                        FROM workflow_runs
                        WHERE status IN ('queued', 'running')
                        ORDER BY created_at ASC;
                        """
                    )
                else:
                    cur.execute(
                        """
                        SELECT run_id, workflow_id, status, orchestration
                        FROM workflow_runs
                        WHERE status IN ('queued', 'running')
                          AND workflow_id = ANY(%s)
                        ORDER BY created_at ASC;
                        """,
                        (workflow_ids,),
                    )
                return [
                    {
                        "run_id": str(row[0]),
                        "workflow_id": str(row[1]),
                        "status": str(row[2]),
                        "orchestration": row[3] or {},
                    }
                    for row in cur.fetchall()
                ]
        finally:
            conn.close()

    def delete_workflow_run(self, run_id: str) -> bool:
        """Delete a workflow run and cascade-delete associated node logs."""
        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM workflow_runs WHERE run_id = %s;", (run_id,))
                deleted = cur.rowcount > 0
            conn.commit()
            return deleted
        finally:
            conn.close()

    def clear_workflow_runs(self) -> int:
        """Delete all workflow runs from database."""
        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM workflow_runs;")
                count = cur.rowcount
            conn.commit()
            return count
        finally:
            conn.close()

    def get_node_execution_logs(self, run_id: str) -> List[Dict[str, Any]]:
        """Get execution logs for all nodes of a given workflow run."""
        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT log_id, run_id, node_id, module_type, batch_index,
                           status, input_payload, config_payload, output, error,
                           cache_hit, outcome, progress, elapsed_ms, cost_usd,
                           usage, started_at, completed_at, created_at
                    FROM node_execution_logs
                    WHERE run_id = %s
                    ORDER BY batch_index ASC, created_at ASC;
                    """,
                    (run_id,),
                )
                rows = cur.fetchall()
                logs = []
                for row in rows:
                    logs.append(
                        {
                            "log_id": row[0],
                            "run_id": row[1],
                            "node_id": row[2],
                            "module_type": row[3],
                            "batch_index": row[4],
                            "status": row[5],
                            "input_payload": row[6],
                            "config_payload": row[7] or {},
                            "output": row[8],
                            "error": row[9],
                            "cache_hit": bool(row[10]),
                            "outcome": row[11],
                            "progress": row[12] or {},
                            "elapsed_ms": row[13],
                            "cost_usd": row[14],
                            "usage": row[15],
                            "started_at": row[16].isoformat()
                            if hasattr(row[16], "isoformat")
                            else str(row[16])
                            if row[16]
                            else None,
                            "completed_at": row[17].isoformat()
                            if hasattr(row[17], "isoformat")
                            else str(row[17])
                            if row[17]
                            else None,
                            "created_at": row[18].isoformat()
                            if hasattr(row[18], "isoformat")
                            else str(row[18]),
                        }
                    )
                return logs
        finally:
            conn.close()


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
