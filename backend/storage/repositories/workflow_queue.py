"""Durable workflow queue, advisory claim, lease, and cancellation capability."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Collection, Dict, Iterator, List, Optional
from uuid import uuid4

import psycopg2.extras

from backend.domains.workflow.application.leases import (
    WorkflowLeaseLost,
    WorkflowRunAlreadyClaimed,
    WorkflowRunLease,
)

from .base import DatabaseConnectionCapability

logger = logging.getLogger(__name__)


class WorkflowRunQueueRepositoryMixin(DatabaseConnectionCapability):
    """Queue claim, lease heartbeat, cancellation, and operational depth access."""

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


__all__ = [
    "WorkflowLeaseLost",
    "WorkflowRunAlreadyClaimed",
    "WorkflowRunLease",
    "WorkflowRunQueueRepositoryMixin",
]
