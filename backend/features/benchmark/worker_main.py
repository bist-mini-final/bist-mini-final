from __future__ import annotations

import logging
from datetime import UTC, datetime
from time import sleep

from backend.bootstrap.container import RuntimeContainer
from backend.core.settings import KUBERNETES_WORKFLOW_QUEUE
from backend.engine.orchestration.kubernetes import KubernetesQueueDispatcher
from backend.engine.worker.base import default_worker_id
from backend.engine.worker.lease import (
    LeaseHeartbeat,
    terminate_process_on_lease_loss,
)
from backend.engine.workflows import DagExecutionCancelled
from backend.features.benchmark.service import (
    BenchmarkRequest,
    execute_benchmark_comparison,
)

from .postgres_store import BenchmarkPostgresStore, ClaimedBenchmarkJob

logger = logging.getLogger(__name__)


def _await_permission(
    store: BenchmarkPostgresStore,
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
    store: BenchmarkPostgresStore,
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


def _run(container: RuntimeContainer) -> int:
    services = container.services
    store = BenchmarkPostgresStore(services.db_manager.database_url)
    worker_id = default_worker_id()
    claimed = store.claim_next(worker_id, datetime.now(UTC))
    if claimed is None:
        print("benchmark queue empty")
        return 0

    dispatcher = KubernetesQueueDispatcher(
        services.workflow_executor,
        services.run_store,
        KUBERNETES_WORKFLOW_QUEUE,
    )
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
            services.workflow_store,
            services.workflow_executor,
            dispatcher,
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


def main() -> int:
    with RuntimeContainer.create(require_database=True) as container:
        return _run(container)


if __name__ == "__main__":
    raise SystemExit(main())
