from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg2
from psycopg2.extras import Json, RealDictCursor

from backend.core.settings import PGVECTOR_URL
from backend.storage.connection_pool import get_pooled_raw_connection


@dataclass(frozen=True, slots=True)
class BenchmarkStoreError(RuntimeError):
    operation: str
    reason: str

    def __str__(self) -> str:
        return f"benchmark PostgreSQL store {self.operation} failed: {self.reason}"


@dataclass(frozen=True, slots=True)
class ClaimedBenchmarkJob:
    job_id: str
    request_payload: dict[str, Any]
    result_rows: tuple[dict[str, Any], ...]
    active_run_id: str | None
    current_payload: dict[str, Any] | None
    worker_id: str


class BenchmarkPostgresStore:
    """Durable benchmark queue and progress store shared by API and worker."""

    def __init__(self, database_url: str = PGVECTOR_URL) -> None:
        self._database_url = database_url

    def enqueue(
        self,
        job_id: str,
        request_payload: dict[str, Any],
        total: int,
        created_at: datetime,
    ) -> dict[str, Any]:
        try:
            with get_pooled_raw_connection(self._database_url) as connection:
                with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        "INSERT INTO benchmark_jobs ("
                        "job_id, request_payload, status, total, available_at, "
                        "created_at, updated_at) VALUES (%s, %s, 'queued', %s, %s, %s, %s) "
                        "RETURNING *",
                        (
                            job_id,
                            Json(request_payload),
                            total,
                            created_at,
                            created_at,
                            created_at,
                        ),
                    )
                    row = cursor.fetchone()
                connection.commit()
        except psycopg2.Error as error:
            raise BenchmarkStoreError("enqueue", str(error)) from error
        if row is None:
            raise BenchmarkStoreError("enqueue", "stored job was not returned")
        return self._public(row)

    def get(self, job_id: str) -> dict[str, Any] | None:
        row = self._fetchone(
            "SELECT * FROM benchmark_jobs WHERE job_id = %s",
            (job_id,),
            "get",
        )
        return self._public(row) if row is not None else None

    def list_results(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._fetchall(
            "SELECT result_payload FROM benchmark_jobs "
            "WHERE status = 'completed' AND result_payload IS NOT NULL "
            "ORDER BY updated_at DESC LIMIT %s",
            (limit,),
            "list_results",
        )
        return [
            {
                "id": payload.get("id"),
                "saved_at": payload.get("saved_at"),
                "summary": payload.get("summary", []),
            }
            for row in rows
            if isinstance((payload := row.get("result_payload")), dict)
        ]

    def get_result(self, benchmark_id: str) -> dict[str, Any] | None:
        row = self._fetchone(
            "SELECT result_payload FROM benchmark_jobs "
            "WHERE result_payload->>'id' = %s LIMIT 1",
            (benchmark_id,),
            "get_result",
        )
        if row is None or not isinstance(row.get("result_payload"), dict):
            return None
        return dict(row["result_payload"])

    def claim_next(
        self,
        worker_id: str,
        claimed_at: datetime,
        *,
        stale_after_seconds: int = 180,
    ) -> ClaimedBenchmarkJob | None:
        try:
            with get_pooled_raw_connection(self._database_url) as connection:
                with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        "WITH candidate AS (SELECT job_id FROM benchmark_jobs "
                        "WHERE (status = 'queued' AND available_at <= %s) OR ("
                        "status IN ('running', 'pausing', 'cancelling') AND "
                        "(heartbeat_at IS NULL OR heartbeat_at < %s - (%s * INTERVAL '1 second'))) "
                        "ORDER BY available_at, created_at, job_id "
                        "FOR UPDATE SKIP LOCKED LIMIT 1) "
                        "UPDATE benchmark_jobs AS job SET "
                        "status = CASE WHEN cancel_requested THEN 'cancelling' ELSE 'running' END, "
                        "worker_id = %s, attempt_count = attempt_count + 1, "
                        "heartbeat_at = %s, updated_at = %s FROM candidate "
                        "WHERE job.job_id = candidate.job_id "
                        "RETURNING job.job_id, job.request_payload, "
                        "job.active_run_id, job.current_payload, job.cancel_requested",
                        (
                            claimed_at,
                            claimed_at,
                            stale_after_seconds,
                            worker_id,
                            claimed_at,
                            claimed_at,
                        ),
                    )
                    row = cursor.fetchone()
                    result_rows: list[dict[str, Any]] = []
                    if row is not None:
                        cursor.execute(
                            "SELECT row_payload FROM benchmark_result_rows "
                            "WHERE job_id = %s ORDER BY created_at, workflow_id, case_id",
                            (row["job_id"],),
                        )
                        result_rows = [
                            dict(result["row_payload"])
                            for result in cursor.fetchall()
                            if isinstance(result.get("row_payload"), dict)
                        ]
                connection.commit()
        except psycopg2.Error as error:
            raise BenchmarkStoreError("claim", str(error)) from error
        if row is None:
            return None
        if bool(row["cancel_requested"]):
            self.finish_cancelled(str(row["job_id"]), worker_id, claimed_at)
            return None
        request_payload = row["request_payload"]
        if not isinstance(request_payload, dict):
            raise BenchmarkStoreError("claim", "invalid persisted benchmark payload")
        return ClaimedBenchmarkJob(
            job_id=str(row["job_id"]),
            request_payload=dict(request_payload),
            result_rows=tuple(result_rows),
            active_run_id=(
                str(row["active_run_id"])
                if row["active_run_id"] is not None
                else None
            ),
            current_payload=(
                dict(row["current_payload"])
                if isinstance(row["current_payload"], dict)
                else None
            ),
            worker_id=worker_id,
        )

    def heartbeat(self, job_id: str, worker_id: str) -> bool:
        return self._owned_update(
            "UPDATE benchmark_jobs SET heartbeat_at = NOW() "
            "WHERE job_id = %s AND worker_id = %s "
            "AND status IN ('running', 'pausing', 'paused', 'cancelling')",
            (job_id, worker_id),
            "heartbeat",
        )

    def control(self, job_id: str, worker_id: str) -> tuple[bool, bool]:
        row = self._fetchone(
            "SELECT cancel_requested, pause_requested FROM benchmark_jobs "
            "WHERE job_id = %s AND worker_id = %s",
            (job_id, worker_id),
            "control",
        )
        if row is None:
            raise BenchmarkStoreError("control", "worker no longer owns benchmark job")
        return bool(row["cancel_requested"]), bool(row["pause_requested"])

    def mark_paused(self, job_id: str, worker_id: str) -> bool:
        return self._owned_update(
            "UPDATE benchmark_jobs SET status = 'paused', updated_at = NOW() "
            "WHERE job_id = %s AND worker_id = %s AND pause_requested = TRUE",
            (job_id, worker_id),
            "mark_paused",
        )

    def mark_running(self, job_id: str, worker_id: str) -> bool:
        return self._owned_update(
            "UPDATE benchmark_jobs SET status = 'running', updated_at = NOW() "
            "WHERE job_id = %s AND worker_id = %s AND pause_requested = FALSE "
            "AND cancel_requested = FALSE",
            (job_id, worker_id),
            "mark_running",
        )

    def update_progress(
        self,
        job_id: str,
        worker_id: str,
        progress: dict[str, Any],
    ) -> bool:
        public_progress = {
            key: progress.get(key)
            for key in (
                "workflow_id",
                "case_id",
                "question",
                "run_id",
            )
        }
        log = {
            "at": datetime.now().astimezone().isoformat(),
            **{
                key: value
                for key, value in progress.items()
                if key not in {"result_row", "run"}
            },
        }
        result_row = progress.get("result_row")
        last_run = progress.get("run")
        try:
            with get_pooled_raw_connection(self._database_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE benchmark_jobs SET completed = %s, total = %s, "
                        "current_payload = %s, active_run_id = %s, "
                        "last_run_payload = COALESCE(%s, last_run_payload), "
                        "logs = logs || %s::jsonb, "
                        "status = CASE WHEN pause_requested THEN 'pausing' "
                        "WHEN cancel_requested THEN 'cancelling' ELSE 'running' END, "
                        "updated_at = NOW() WHERE job_id = %s AND worker_id = %s",
                        (
                            int(progress.get("completed", 0)),
                            int(progress.get("total", 1)),
                            Json(public_progress),
                            progress.get("run_id"),
                            Json(last_run) if last_run is not None else None,
                            Json([log]),
                            job_id,
                            worker_id,
                        ),
                    )
                    updated = cursor.rowcount == 1
                    if updated:
                        if isinstance(result_row, dict):
                            workflow_id = result_row.get("workflow_id")
                            case_id = result_row.get("case_id")
                            if not isinstance(workflow_id, str) or not isinstance(
                                case_id,
                                str,
                            ):
                                raise BenchmarkStoreError(
                                    "update_progress",
                                    "result row is missing workflow_id or case_id",
                                )
                            cursor.execute(
                                "INSERT INTO benchmark_result_rows ("
                                "job_id, workflow_id, case_id, row_payload) "
                                "VALUES (%s, %s, %s, %s) "
                                "ON CONFLICT (job_id, workflow_id, case_id) "
                                "DO UPDATE SET row_payload = EXCLUDED.row_payload, "
                                "updated_at = NOW()",
                                (
                                    job_id,
                                    workflow_id,
                                    case_id,
                                    Json(result_row),
                                ),
                            )
                        cursor.execute(
                            "UPDATE benchmark_jobs SET logs = ("
                            "SELECT COALESCE(jsonb_agg(value ORDER BY ordinal), '[]'::jsonb) "
                            "FROM jsonb_array_elements(logs) WITH ORDINALITY "
                            "AS item(value, ordinal) WHERE ordinal > "
                            "GREATEST(jsonb_array_length(logs) - 80, 0)"
                            ") WHERE job_id = %s",
                            (job_id,),
                        )
                connection.commit()
        except psycopg2.Error as error:
            raise BenchmarkStoreError("update_progress", str(error)) from error
        return updated

    def request_pause(self, job_id: str) -> dict[str, Any] | None:
        return self._control_update(
            job_id,
            "pause_requested = TRUE, status = CASE WHEN status = 'queued' "
            "THEN 'paused' ELSE 'pausing' END",
            ("queued", "running", "pausing"),
            "pause",
        )

    def request_resume(self, job_id: str) -> dict[str, Any] | None:
        return self._control_update(
            job_id,
            "pause_requested = FALSE, status = CASE WHEN worker_id IS NULL "
            "THEN 'queued' ELSE 'running' END, available_at = NOW()",
            ("paused", "pausing"),
            "resume",
        )

    def request_cancel(self, job_id: str) -> dict[str, Any] | None:
        return self._control_update(
            job_id,
            "cancel_requested = TRUE, pause_requested = FALSE, "
            "status = CASE WHEN status IN ('queued', 'paused') "
            "THEN 'cancelled' ELSE 'cancelling' END, "
            "worker_id = CASE WHEN status IN ('queued', 'paused') THEN NULL ELSE worker_id END",
            ("queued", "running", "pausing", "paused"),
            "cancel",
        )

    def finish_completed(
        self,
        job_id: str,
        worker_id: str,
        result: dict[str, Any],
        completed_at: datetime,
    ) -> bool:
        return self._owned_update(
            "UPDATE benchmark_jobs SET status = 'completed', completed = total, "
            "current_payload = NULL, active_run_id = NULL, result_payload = %s, "
            "worker_id = NULL, heartbeat_at = NULL, updated_at = %s "
            "WHERE job_id = %s AND worker_id = %s AND cancel_requested = FALSE",
            (Json(result), completed_at, job_id, worker_id),
            "complete",
        )

    def finish_cancelled(
        self,
        job_id: str,
        worker_id: str,
        completed_at: datetime,
    ) -> bool:
        return self._owned_update(
            "UPDATE benchmark_jobs SET status = 'cancelled', active_run_id = NULL, "
            "worker_id = NULL, heartbeat_at = NULL, updated_at = %s "
            "WHERE job_id = %s AND worker_id = %s",
            (completed_at, job_id, worker_id),
            "cancelled",
        )

    def finish_failed(
        self,
        job_id: str,
        worker_id: str,
        error_message: str,
        completed_at: datetime,
    ) -> bool:
        return self._owned_update(
            "UPDATE benchmark_jobs SET status = 'failed', error = %s, "
            "active_run_id = NULL, worker_id = NULL, heartbeat_at = NULL, "
            "updated_at = %s WHERE job_id = %s AND worker_id = %s",
            (error_message[:4000], completed_at, job_id, worker_id),
            "fail",
        )

    def _control_update(
        self,
        job_id: str,
        assignments: str,
        allowed_statuses: tuple[str, ...],
        operation: str,
    ) -> dict[str, Any] | None:
        try:
            with get_pooled_raw_connection(self._database_url) as connection:
                with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        f"UPDATE benchmark_jobs SET {assignments}, updated_at = NOW() "
                        "WHERE job_id = %s AND status = ANY(%s) RETURNING *",
                        (job_id, list(allowed_statuses)),
                    )
                    row = cursor.fetchone()
                connection.commit()
        except psycopg2.Error as error:
            raise BenchmarkStoreError(operation, str(error)) from error
        return self._public(row) if row is not None else None

    def _owned_update(
        self,
        query: str,
        parameters: tuple[object, ...],
        operation: str,
    ) -> bool:
        try:
            with get_pooled_raw_connection(self._database_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(query, parameters)
                    updated = cursor.rowcount == 1
                connection.commit()
        except psycopg2.Error as error:
            raise BenchmarkStoreError(operation, str(error)) from error
        return updated

    def _fetchone(
        self,
        query: str,
        parameters: tuple[object, ...],
        operation: str,
    ) -> dict[str, Any] | None:
        rows = self._query(query, parameters, operation, fetch_all=False)
        return rows if isinstance(rows, dict) else None

    def _fetchall(
        self,
        query: str,
        parameters: tuple[object, ...],
        operation: str,
    ) -> list[dict[str, Any]]:
        rows = self._query(query, parameters, operation, fetch_all=True)
        return rows if isinstance(rows, list) else []

    def _query(
        self,
        query: str,
        parameters: tuple[object, ...],
        operation: str,
        *,
        fetch_all: bool,
    ) -> dict[str, Any] | list[dict[str, Any]] | None:
        try:
            with get_pooled_raw_connection(self._database_url) as connection:
                with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(query, parameters)
                    return cursor.fetchall() if fetch_all else cursor.fetchone()
        except psycopg2.Error as error:
            raise BenchmarkStoreError(operation, str(error)) from error

    @staticmethod
    def _public(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(row["job_id"]),
            "status": str(row["status"]),
            "completed": int(row["completed"]),
            "total": int(row["total"]),
            "current": row.get("current_payload"),
            "active_run_id": row.get("active_run_id"),
            "last_run": row.get("last_run_payload"),
            "logs": row.get("logs") or [],
            "result": row.get("result_payload"),
            "error": row.get("error"),
        }


__all__ = [
    "BenchmarkPostgresStore",
    "BenchmarkStoreError",
    "ClaimedBenchmarkJob",
]
