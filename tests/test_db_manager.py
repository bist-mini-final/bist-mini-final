"""Focused tests for source-file deletion resolution."""

from uuid import uuid4

import pytest

from backend.core.settings import PGVECTOR_URL
from backend.storage.db_manager import (
    DatabaseManager,
    WorkflowLeaseLost,
    WorkflowRunAlreadyClaimed,
)


class FakeCursor:
    def __init__(self, *, direct_deleted=0, filename_matches=()):
        self.direct_deleted = direct_deleted
        self.filename_matches = list(filename_matches)
        self.rowcount = 0
        self.executions = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, query, params=None):
        """
        Record a normalized query and update the simulated affected-row count.
        
        Parameters:
        	query (str): The SQL query to record.
        	params (object, optional): Parameters associated with the query.
        """
        normalized = " ".join(query.split())
        self.executions.append((normalized, params))
        if "WHERE file_id = %s OR file_hash = %s" in normalized:
            self.rowcount = self.direct_deleted
        elif normalized.startswith("DELETE FROM source_files WHERE file_id = %s"):
            self.rowcount = 1
        else:
            self.rowcount = 0

    def fetchmany(self, size):
        return self.filename_matches[:size]

    def fetchone(self):
        return None


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False
        self.closed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


def database_with(cursor):
    database = DatabaseManager("postgresql://mock:5432/mock")
    connection = FakeConnection(cursor)
    database._raw_connection = lambda: connection
    database._advisory_lock_connection = lambda: connection
    return database, connection


def test_init_does_not_perform_db_io(monkeypatch):
    called = False

    def mock_connect(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("Connection should not be attempted on init")

    monkeypatch.setattr("psycopg2.connect", mock_connect)
    manager = DatabaseManager("postgresql://mock:5432/mock")
    assert manager.database_url == "postgresql://mock:5432/mock"
    assert called is False


def test_delete_source_file_resolves_unique_filename_to_one_id():
    cursor = FakeCursor(filename_matches=[("file-id-1",)])
    database, connection = database_with(cursor)

    assert database.delete_source_file("folder/sample.xlsx") is True
    assert cursor.executions[-1][1] == ("file-id-1",)
    assert connection.committed is True
    assert connection.closed is True


def test_delete_source_file_rejects_ambiguous_filename():
    cursor = FakeCursor(filename_matches=[("file-id-1",), ("file-id-2",)])
    database, connection = database_with(cursor)

    with pytest.raises(ValueError, match="file_id 또는 file_hash"):
        database.delete_source_file("sample.xlsx")

    assert len(cursor.executions) == 2
    assert connection.committed is False
    assert connection.closed is True


def test_delete_source_file_keeps_direct_id_or_hash_deletion():
    cursor = FakeCursor(direct_deleted=1)
    database, connection = database_with(cursor)

    assert database.delete_source_file("a" * 64) is True
    assert len(cursor.executions) == 1
    assert "file_hash" in cursor.executions[0][0]
    assert connection.committed is True


def test_is_connected_success_closes_connection():
    cursor = FakeCursor()
    database, connection = database_with(cursor)

    assert database.is_connected() is True
    assert connection.closed is True


def test_is_connected_error_closes_connection():
    class ErrorCursor(FakeCursor):
        def execute(self, query, params=None):
            """Simulate a database execution failure.
            
            Raises:
                RuntimeError: Always, indicating that the database connection was lost.
            """
            raise RuntimeError("DB connection lost")

    cursor = ErrorCursor()
    database, connection = database_with(cursor)

    assert database.is_connected() is False
    assert connection.closed is True


def test_ensure_schema_closes_connection_on_success():
    cursor = FakeCursor()
    database, connection = database_with(cursor)

    database.ensure_schema()
    assert connection.committed is True
    assert connection.closed is True
    # Ensure no destructive ALTER TABLE DROP COLUMN in ensure_schema
    executed_queries = " ".join(e[0] for e in cursor.executions)
    assert "DROP COLUMN" not in executed_queries


def test_ensure_schema_logs_and_closes_connection_on_error():
    class ErrorCursor(FakeCursor):
        def execute(self, query, params=None):
            raise RuntimeError("Schema init error")

    cursor = ErrorCursor()
    database, connection = database_with(cursor)

    database.ensure_schema()
    assert connection.committed is False
    assert connection.closed is True


def test_run_migrations_closes_connection_on_success():
    cursor = FakeCursor()
    database, connection = database_with(cursor)

    database.run_migrations()
    assert connection.committed is True
    assert connection.closed is True
    executed_queries = " ".join(e[0] for e in cursor.executions)
    assert "DROP COLUMN IF EXISTS file_content" in executed_queries


def test_run_migrations_logs_and_closes_connection_on_error():
    class ErrorCursor(FakeCursor):
        def execute(self, query, params=None):
            raise RuntimeError("Migration error")

    cursor = ErrorCursor()
    database, connection = database_with(cursor)


def test_claim_workflow_run_holds_and_releases_advisory_lock():
    class ClaimCursor(FakeCursor):
        def __init__(self):
            super().__init__()
            self.results = [(True,), (True,)]

        def fetchone(self):
            return self.results.pop(0)

    cursor = ClaimCursor()
    database, connection = database_with(cursor)

    with database.claim_workflow_run("run-claimed"):
        assert connection.closed is False

    assert connection.closed is True
    assert "pg_try_advisory_lock" in cursor.executions[0][0]
    assert "pg_advisory_unlock" in cursor.executions[1][0]


def test_claim_workflow_run_rejects_duplicate_owner():
    class ClaimCursor(FakeCursor):
        def fetchone(self):
            return (False,)

    cursor = ClaimCursor()
    database, connection = database_with(cursor)

    with pytest.raises(WorkflowRunAlreadyClaimed):
        with database.claim_workflow_run("run-claimed"):
            pass

    assert connection.closed is True


def test_claim_next_workflow_run_uses_skip_locked_and_stable_job_identity():
    class QueueCursor(FakeCursor):
        def fetchone(self):
            return ("run-queued",)

    cursor = QueueCursor()
    database, connection = database_with(cursor)

    claimed = database.claim_next_workflow_run(
        "excel-ingestion",
        "excel-ingestion-job-abc",
        stale_after_seconds=180,
    )

    assert claimed is not None
    assert claimed.run_id == "run-queued"
    assert len(claimed.token) == 32
    query, params = cursor.executions[0]
    assert "FOR UPDATE SKIP LOCKED" in query
    assert "heartbeat_at" in query
    assert params == (
        "excel-ingestion",
        [],
        "excel-ingestion-job-abc",
        180,
        "excel-ingestion-job-abc",
    )
    assert connection.committed is True
    assert connection.closed is True


def test_enqueue_workflow_run_sets_kubernetes_queue_metadata():
    class EnqueueCursor(FakeCursor):
        def execute(self, query, params=None):
            super().execute(query, params)
            self.rowcount = 1

    cursor = EnqueueCursor()
    database, connection = database_with(cursor)

    assert database.enqueue_workflow_run(
        "run-queued",
        "excel-ingestion",
        submission_attempt=2,
        submitted_at="2026-08-20T00:00:00+00:00",
        priority=5,
    ) is True

    query, params = cursor.executions[0]
    assert "WHERE run_id = %s AND cancel_requested = FALSE" in query
    assert "cancel_requested = FALSE," not in query
    assert "'backend', 'kubernetes'" in query
    assert params == (
        "excel-ingestion",
        5,
        "excel-ingestion",
        2,
        "2026-08-20T00:00:00+00:00",
        "run-queued",
    )
    assert connection.committed is True


def test_enqueue_workflow_run_preserves_existing_cancellation():
    class CancelledEnqueueCursor(FakeCursor):
        def __init__(self):
            super().__init__()
            self.cancel_lookup = False

        def execute(self, query, params=None):
            super().execute(query, params)
            self.cancel_lookup = query.lstrip().startswith(
                "SELECT cancel_requested"
            )
            self.rowcount = 0

        def fetchone(self):
            return (True,) if self.cancel_lookup else None

    cursor = CancelledEnqueueCursor()
    database, connection = database_with(cursor)

    enqueued = database.enqueue_workflow_run(
        "run-cancelled",
        "excel-ingestion",
        submission_attempt=2,
        submitted_at="2026-08-20T00:00:00+00:00",
    )

    assert enqueued is False
    update_query = cursor.executions[0][0]
    assert "WHERE run_id = %s AND cancel_requested = FALSE" in update_query
    assert "cancel_requested = FALSE," not in update_query
    assert connection.committed is True


def test_stale_recovery_keeps_lease_while_existing_advisory_owner_runs():
    database = DatabaseManager(PGVECTOR_URL)
    if not database.is_connected():
        pytest.skip("PostgreSQL integration database is unavailable")
    if not database.ensure_schema():
        pytest.skip("PostgreSQL integration schema is unavailable")

    run_id = f"lease-integration-{uuid4().hex}"
    queue_name = "lease-integration"
    run = {
        "id": run_id,
        "workflow_id": "lease-integration",
        "status": "queued",
        "orchestration": {},
        "batches": [],
        "nodes": {
            "node-1": {
                "node_id": "node-1",
                "module_type": "test",
                "status": "running",
                "progress": {"completed_items": 0, "total_items": 1},
            }
        },
    }
    try:
        database.save_workflow_run(run)
        assert database.enqueue_workflow_run(
            run_id,
            queue_name,
            submission_attempt=1,
            submitted_at="2026-08-21T00:00:00+00:00",
        )
        original = database.claim_next_workflow_run(queue_name, "worker-old")
        assert original is not None

        with database.claim_workflow_run(
            run_id,
            queue_name=queue_name,
            worker_id="worker-old",
            lease_token=original.token,
        ):
            conn = database._raw_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE workflow_runs
                        SET heartbeat_at = NOW() - INTERVAL '10 minutes'
                        WHERE run_id = %s;
                        """,
                        (run_id,),
                    )
                conn.commit()
            finally:
                conn.close()

            recovery = database.claim_next_workflow_run(
                queue_name,
                "worker-recovery",
                stale_after_seconds=1,
            )
            assert recovery is not None
            with pytest.raises(WorkflowRunAlreadyClaimed):
                with database.claim_workflow_run(
                    run_id,
                    queue_name=queue_name,
                    worker_id="worker-recovery",
                    lease_token=recovery.token,
                    stale_after_seconds=1,
                ):
                    pass

            with pytest.raises(WorkflowLeaseLost):
                database.save_workflow_node_progress(
                    run,
                    "node-1",
                    lease_token=recovery.token,
                )

            conn = database._raw_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT worker_id, lease_token
                        FROM workflow_runs
                        WHERE run_id = %s;
                        """,
                        (run_id,),
                    )
                    owner = cur.fetchone()
            finally:
                conn.close()
            assert owner == ("worker-old", original.token)
    finally:
        database.delete_workflow_run(run_id)


def test_cancel_request_is_durable_across_api_and_worker_processes():
    class CancelCursor(FakeCursor):
        def execute(self, query, params=None):
            super().execute(query, params)
            self.rowcount = 1

    cursor = CancelCursor()
    database, connection = database_with(cursor)

    assert database.request_workflow_cancel("run-active") is True

    query, params = cursor.executions[0]
    assert "cancel_requested = TRUE" in query
    assert "THEN 'paused'" in query
    assert params == ("run-active",)
    assert connection.committed is True


def test_pending_run_references_do_not_select_large_node_payloads():
    class ReferenceCursor(FakeCursor):
        def fetchall(self):
            return [
                (
                    "run-pending",
                    "indexing_pgvector",
                    "queued",
                    {"backend": "kubernetes", "external_run_id": "job-1"},
                )
            ]

    cursor = ReferenceCursor()
    database, connection = database_with(cursor)

    references = database.list_pending_workflow_run_references(
        ["indexing_pgvector"]
    )

    assert references[0]["run_id"] == "run-pending"
    query = cursor.executions[0][0]
    assert "orchestration" in query
    assert "nodes" not in query
    assert "graph" not in query
    assert connection.closed is True


def test_workflow_run_summary_uses_node_logs_without_large_payload_columns():
    class SummaryCursor(FakeCursor):
        def __init__(self):
            super().__init__()
            self.mode = ""

        def execute(self, query, params=None):
            super().execute(query, params)
            normalized = " ".join(query.split())
            if "FROM workflow_runs" in normalized:
                self.mode = "run"
            elif "FROM node_execution_logs" in normalized:
                self.mode = "nodes"

        def fetchone(self):
            if self.mode != "run":
                return None
            return (
                "run-summary",
                "indexing_pgvector",
                "2026-08-20T00:00:00+00:00",
                "running",
                1,
                {"nodes": [], "edges": []},
                {},
                True,
                {"backend": "kubernetes", "external_run_id": "job-1"},
                [],
                "2026-08-20T00:00:00+00:00",
                "2026-08-20T00:00:01+00:00",
            )

        def fetchall(self):
            if self.mode != "nodes":
                return []
            return [
                (
                    "run-summary",
                    "embedder",
                    "cell_text_embedder",
                    0,
                    "succeeded",
                    {"batch_size": 128},
                    None,
                    None,
                    False,
                    "generated",
                    {
                        "phase": "embedding_batches",
                        "completed_batches": 2,
                        "total_batches": 2,
                    },
                    1234.0,
                    None,
                    None,
                    "2026-08-20T00:00:00+00:00",
                    "2026-08-20T00:00:01+00:00",
                )
            ]

    cursor = SummaryCursor()
    database, connection = database_with(cursor)

    summary = database.get_workflow_run_summary("run-summary")

    assert summary is not None
    assert summary["status"] == "completed"
    assert summary["nodes"]["embedder"]["progress"]["completed_batches"] == 2
    run_query, node_query = (execution[0] for execution in cursor.executions)
    assert "nodes" not in run_query
    assert "input_payload" not in node_query
    assert "cell_text_embedder" not in node_query
    assert connection.closed is True


def test_save_and_get_workflow_run():
    class RunCursor(FakeCursor):
        def __init__(self):
            super().__init__()
            self.stored_row = None

        def execute(self, query, params=None):
            normalized = " ".join(query.split())
            self.executions.append((normalized, params))
            if normalized.startswith("INSERT INTO workflow_runs"):
                self.stored_row = (
                    params[0], params[1], params[2], params[3], params[4],
                    {"nodes": [], "edges": []}, {}, params[7],
                    {"backend": "kubernetes", "external_run_id": "job-run-1"},
                    [], {"node-1": {"status": "succeeded"}},
                    "2026-08-20T00:00:00+00:00", "2026-08-20T00:00:00+00:00"
                )
            elif normalized.startswith("DELETE FROM workflow_runs WHERE run_id"):
                self.rowcount = 1
            elif normalized.startswith("DELETE FROM workflow_runs"):
                self.rowcount = 3

        def fetchone(self):
            return self.stored_row

        def fetchall(self):
            return [self.stored_row] if self.stored_row else []

    cursor = RunCursor()
    database, connection = database_with(cursor)

    sample_run = {
        "id": "run-test-123",
        "workflow_id": "indexing_pgvector",
        "status": "completed",
        "orchestration": {
            "backend": "kubernetes",
            "external_run_id": "job-run-1",
        },
        "nodes": {
            "node-1": {
                "node_id": "node-1",
                "module_type": "processed_file_selector",
                "status": "succeeded",
                "progress": {"completed_batches": 1, "total_batches": 1},
            }
        },
    }

    database.save_workflow_run(sample_run)
    assert connection.committed is True
    assert len(cursor.executions) == 2  # 1 for workflow_runs, 1 for node_execution_logs

    loaded = database.get_workflow_run("run-test-123")
    assert loaded is not None
    assert loaded["id"] == "run-test-123"
    assert loaded["workflow_id"] == "indexing_pgvector"
    assert loaded["orchestration"]["external_run_id"] == "job-run-1"

    listed = database.list_workflow_runs("indexing_pgvector")
    assert len(listed) == 1
    assert listed[0]["id"] == "run-test-123"

    assert database.delete_workflow_run("run-test-123") is True
    assert database.clear_workflow_runs() == 3
