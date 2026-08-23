"""Submit product runs to a durable PostgreSQL queue watched by KEDA."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Collection, Optional

from backend.engine.workflows.executor import WorkflowExecutor
from backend.engine.workflows.models import WorkflowRun, utc_now_iso
from backend.engine.workflows.store import RunStore

logger = logging.getLogger(__name__)


@dataclass
class KubernetesQueueDispatcher:
    """Queue adapter; KEDA and Kubernetes own scaling and placement."""

    executor: WorkflowExecutor
    run_store: RunStore
    queue_name: str

    def submit(self, run_id: str, *, resume_failed: bool = False) -> bool:
        run = self.run_store.load_summary(run_id)
        if resume_failed and run.status in ("failed", "paused"):
            self.executor.prepare_resume(run_id)
            run = self.run_store.load_summary(run_id)
        if run.status == "completed":
            return False
        if (
            run.orchestration.backend == "kubernetes"
            and run.orchestration.deployment_name == self.queue_name
            and run.orchestration.submitted_at is not None
            and run.status in ("queued", "running")
        ):
            return False
        if run.status in ("failed", "paused"):
            self.executor.prepare_resume(run_id)
            run = self.run_store.load_summary(run_id)

        submission_attempt = run.orchestration.submission_attempt + 1
        enqueued = self.run_store.enqueue(
            run_id,
            self.queue_name,
            submission_attempt=submission_attempt,
            submitted_at=utc_now_iso(),
        )
        return enqueued

    def cancel(self, run_id: str) -> WorkflowRun:
        if not self.run_store.request_cancel(run_id):
            raise RuntimeError(
                "Kubernetes 배치 작업을 취소하려면 PostgreSQL 연결이 필요합니다"
            )
        # This is relevant only when tests or development execute the same run
        # in-process; an external worker observes the durable DB flag.
        self.executor.request_cancel(run_id)
        return self.run_store.load_summary(run_id)

    def cancel_all(self) -> int:
        cancelled = 0
        for run in self.run_store.list_summaries():
            if run.status not in ("queued", "running"):
                continue
            if run.orchestration.backend != "kubernetes":
                continue
            self.cancel(run.id)
            cancelled += 1
        return cancelled

    def recover_pending(
        self,
        workflow_ids: Optional[Collection[str]] = None,
        max_recoveries: int = 100,
    ) -> int:
        """Enqueue unowned current-schema runs; stale leases recover in PostgreSQL."""

        allowed = set(workflow_ids) if workflow_ids is not None else None
        recovered = 0
        database = self.run_store.db_manager
        if database is not None:
            references = database.list_pending_workflow_run_references(
                sorted(allowed) if allowed is not None else None
            )
            for reference in references:
                if recovered >= max_recoveries:
                    break
                orchestration = reference["orchestration"]
                if (
                    orchestration.get("backend") == "kubernetes"
                    and orchestration.get("deployment_name") == self.queue_name
                ):
                    continue
                try:
                    if self.submit(reference["run_id"]):
                        recovered += 1
                except Exception:
                    logger.warning(
                        "미완료 run 큐 복구 실패 (run_id=%s)",
                        reference["run_id"],
                        exc_info=True,
                    )
            return recovered

        # A database is mandatory for cross-container execution. Let startup
        # remain available, but leave pending runs untouched and visible.
        logger.warning("PostgreSQL이 연결되지 않아 Kubernetes 큐 복구를 건너뜁니다")
        return 0

    def is_active(self, run_id: str) -> bool:
        run = self.run_store.load_summary(run_id)
        return (
            run.orchestration.backend == "kubernetes"
            and run.orchestration.external_run_id is not None
            and run.status == "running"
        )

    def shutdown(self) -> None:
        return None
