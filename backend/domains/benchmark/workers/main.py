from __future__ import annotations

import logging
from datetime import UTC, datetime
from time import sleep

from backend.domains.benchmark.application.execution import execute_benchmark_comparison
from backend.domains.benchmark.application.ports import BenchmarkWorkerStorePort
from backend.domains.benchmark.domain import BenchmarkRequest, ClaimedBenchmarkJob
from backend.domains.workflow.application.dispatching import RunDispatcher
from backend.domains.workflow.application.executor import WorkflowExecutor
from backend.domains.workflow.application.ports import WorkflowDefinitionRepository
from backend.domains.workflow.domain import DagExecutionCancelled
from backend.shared.application.leases import (
    LeaseHeartbeat,
    terminate_process_on_lease_loss,
)
from backend.shared.application.workers import default_worker_id

logger = logging.getLogger(__name__)


def _await_permission(
    store: BenchmarkWorkerStorePort,
    claimed: ClaimedBenchmarkJob,
    worker_id: str,
    heartbeat: LeaseHeartbeat,
) -> None:
    announced_pause = False
    while True:
        heartbeat.raise_if_lost()
        cancel_requested, pause_requested = store.control(claimed.job_id, worker_id)
        if cancel_requested:
            raise DagExecutionCancelled("벤치마크 실행이 중지되었습니다")
        if not pause_requested:
            if announced_pause:
                store.mark_running(claimed.job_id, worker_id)
            return
        if not announced_pause:
            store.mark_paused(claimed.job_id, worker_id)
            announced_pause = True
        sleep(0.25)


def _update_progress(
    store: BenchmarkWorkerStorePort,
    claimed: ClaimedBenchmarkJob,
    worker_id: str,
    heartbeat: LeaseHeartbeat,
    progress: dict[str, object],
) -> None:
    heartbeat.raise_if_lost()
    if not store.update_progress(claimed.job_id, worker_id, progress):
        raise RuntimeError("benchmark worker lease changed")


def _resume_active(claimed: ClaimedBenchmarkJob) -> tuple[str, str, str] | None:
    current = claimed.current_payload or {}
    if (
        claimed.active_run_id is None
        or not isinstance(current.get("workflow_id"), str)
        or not isinstance(current.get("case_id"), str)
    ):
        return None
    return (
        str(current["workflow_id"]),
        str(current["case_id"]),
        claimed.active_run_id,
    )


def main(
    *,
    store: BenchmarkWorkerStorePort,
    workflow_store: WorkflowDefinitionRepository,
    workflow_executor: WorkflowExecutor,
    workflow_dispatcher: RunDispatcher,
) -> int:
    worker_id = default_worker_id()
    claimed = store.claim_next(worker_id, datetime.now(UTC))
    if claimed is None:
        print("benchmark queue empty")
        return 0

    heartbeat = LeaseHeartbeat(
        lambda: store.heartbeat(claimed.job_id, worker_id),
        interval_seconds=30,
        thread_name=f"benchmark-heartbeat-{claimed.job_id}",
        logger=logger,
        failure_message=f"benchmark heartbeat failed (job_id={claimed.job_id})",
        on_lease_lost=terminate_process_on_lease_loss,
    )
    heartbeat.start()

    def await_permission() -> None:
        _await_permission(store, claimed, worker_id, heartbeat)

    def update(progress: dict[str, object]) -> None:
        _update_progress(store, claimed, worker_id, heartbeat, progress)

    try:
        result = execute_benchmark_comparison(
            BenchmarkRequest.model_validate(claimed.request_payload),
            workflow_store,
            workflow_executor,
            workflow_dispatcher,
            update,
            await_permission,
            claimed.result_rows,
            _resume_active(claimed),
        )
        completed_at = datetime.now(UTC)
        result_record = {
            "id": f"benchmark-{claimed.job_id.removeprefix('benchmark-job-')}",
            "saved_at": completed_at.isoformat(),
            **result,
        }
        await_permission()
        if not store.finish_completed(
            claimed.job_id,
            worker_id,
            result_record,
            completed_at,
        ):
            raise RuntimeError("benchmark completion lease changed")
    except DagExecutionCancelled:
        store.finish_cancelled(claimed.job_id, worker_id, datetime.now(UTC))
        return 0
    except Exception as error:
        logger.exception("benchmark worker failed (job_id=%s)", claimed.job_id)
        store.finish_failed(
            claimed.job_id,
            worker_id,
            str(error) or type(error).__name__,
            datetime.now(UTC),
        )
        return 1
    finally:
        heartbeat.stop()

    print(f"benchmark {claimed.job_id} completed")
    return 0
