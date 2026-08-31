"""Claim and execute exactly one PostgreSQL-queued workflow run in Kubernetes/local worker."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import time
from collections.abc import Sequence
from contextlib import contextmanager
from typing import Any, Generator, Optional, Protocol

from backend.domains.workflow.application.leases import (
    WorkflowRunAlreadyClaimed,
    WorkflowRunLease,
)
from backend.domains.workflow.application.module_registry import ModuleRegistryPort
from backend.domains.workflow.application.task_plan import compile_task_plan
from backend.domains.workflow.domain import DagExecutionCancelled
from backend.shared.application.leases import (
    LeaseHeartbeat,
    terminate_process_on_lease_loss,
)

logger = logging.getLogger(__name__)


class WorkflowWorkerServices(Protocol):
    module_registry: ModuleRegistryPort
    workflow_executor: Any
    run_store: Any
    workflow_runs: Any


class ModuleTaskTimeout(TimeoutError):
    """Raised when one module exceeds its declared task timeout."""


@contextmanager
def task_timeout(seconds: Optional[float]) -> Generator[None, None, None]:
    """Apply a per-module wall-clock timeout in the worker's main thread."""
    setitimer = getattr(signal, "setitimer", None)
    sigalrm = getattr(signal, "SIGALRM", None)
    itimer_real = getattr(signal, "ITIMER_REAL", None)
    if (
        seconds is None
        or not callable(setitimer)
        or sigalrm is None
        or itimer_real is None
    ):
        yield
        return

    def _timeout_handler(_signum: int, _frame: object) -> None:
        raise ModuleTaskTimeout(f"모듈 실행 제한 시간 {seconds:g}초를 초과했습니다")

    previous_handler = signal.getsignal(sigalrm)
    signal.signal(sigalrm, _timeout_handler)
    setitimer(itimer_real, seconds)
    try:
        yield
    finally:
        setitimer(itimer_real, 0)
        signal.signal(sigalrm, previous_handler)


def execute_with_policy(
    services: WorkflowWorkerServices,
    run_id: str,
    node_id: str,
    retries: int,
    retry_delay_seconds: float,
    timeout_seconds: Optional[float],
) -> None:
    """Execute one node and apply its portable retry/timeout policy."""
    for attempt in range(retries + 1):
        try:
            with task_timeout(timeout_seconds):
                services.workflow_executor.execute_scheduled_node(run_id, node_id)
            return
        except DagExecutionCancelled:
            raise
        except Exception:
            if attempt >= retries:
                raise
            logger.warning(
                "모듈 실행 재시도 %d/%d (run=%s, node=%s)",
                attempt + 1,
                retries,
                run_id,
                node_id,
                exc_info=True,
            )
            if retry_delay_seconds:
                time.sleep(retry_delay_seconds)


def _execute_claim(
    services: WorkflowWorkerServices,
    claim: WorkflowRunLease,
    queue_name: str,
    worker_id: str,
    stale_after_seconds: int,
    heartbeat_seconds: float,
) -> str:
    """Execute one selected lease generation while holding its advisory lock."""
    run_id = claim.run_id
    lease_token = claim.token
    try:
        with services.workflow_runs.claim_workflow_run(
            run_id,
            queue_name=queue_name,
            worker_id=worker_id,
            lease_token=lease_token,
            stale_after_seconds=stale_after_seconds,
        ):
            with services.run_store.workflow_lease(run_id, lease_token):
                heartbeat = LeaseHeartbeat(
                    lambda: services.workflow_runs.heartbeat_workflow_run(
                        run_id,
                        worker_id,
                        lease_token,
                    ),
                    interval_seconds=heartbeat_seconds,
                    thread_name="workflow-lease-heartbeat",
                    logger=logger,
                    failure_message="워크플로 lease heartbeat 실패",
                    on_lease_lost=terminate_process_on_lease_loss,
                )
                heartbeat.start()
                try:
                    run = services.run_store.load(run_id)
                    plan = compile_task_plan(run, services.module_registry)
                    batches: dict[int, list[str]] = {}
                    planned_by_node = {
                        planned.node_id: planned for planned in plan
                    }
                    for planned in plan:
                        batches.setdefault(planned.batch_index, []).append(
                            planned.node_id
                        )
                    for batch_index in sorted(batches):
                        heartbeat.raise_if_lost()
                        batch_plan = tuple(
                            planned_by_node[node_id]
                            for node_id in batches[batch_index]
                        )
                        if any(
                            item.policy.timeout_seconds is not None
                            for item in batch_plan
                        ):
                            # Signal-based hard timeouts require the main thread.
                            for item in batch_plan:
                                policy = item.policy
                                execute_with_policy(
                                    services,
                                    run_id,
                                    item.node_id,
                                    policy.retries,
                                    policy.retry_delay_seconds,
                                    policy.timeout_seconds,
                                )
                        else:
                            services.workflow_executor.execute_scheduled_batch(
                                run_id,
                                tuple(item.node_id for item in batch_plan),
                            )
                    heartbeat.raise_if_lost()
                    completed = services.run_store.load(run_id)
                    if completed.status != "completed":
                        raise RuntimeError(
                            f"배치 run이 완료되지 않았습니다: {completed.status}"
                        )
                    logger.info(
                        "배치 run 완료 (run=%s, modules=%d)",
                        run_id,
                        len(plan),
                    )
                    return run_id
                finally:
                    heartbeat.stop()
    except DagExecutionCancelled:
        logger.info("배치 run 취소 완료 (run=%s)", run_id)
        return run_id
    except WorkflowRunAlreadyClaimed:
        raise
    except Exception as error:
        try:
            services.workflow_runs.fail_workflow_run_claim(
                run_id,
                worker_id,
                lease_token,
                str(error),
            )
        except Exception:
            logger.warning("치명적 worker 오류 상태 저장 실패", exc_info=True)
        raise


def run_one(
    queue_name: str,
    worker_id: str,
    *,
    services: WorkflowWorkerServices,
    stale_after_seconds: int = 180,
    heartbeat_seconds: float = 15,
) -> Optional[str]:
    """Claim and finish one item; skip candidates still owned by another worker."""
    excluded_run_ids: list[str] = []
    while True:
        claim = services.workflow_runs.claim_next_workflow_run(
            queue_name,
            worker_id,
            stale_after_seconds=stale_after_seconds,
            excluded_run_ids=tuple(excluded_run_ids),
        )
        if claim is None:
            logger.info("claim 가능한 작업이 없어 종료합니다 (queue=%s)", queue_name)
            return None
        try:
            return _execute_claim(
                services,
                claim,
                queue_name,
                worker_id,
                stale_after_seconds,
                heartbeat_seconds,
            )
        except WorkflowRunAlreadyClaimed:
            excluded_run_ids.append(claim.run_id)
            logger.info(
                "advisory lock 사용 중인 후보를 건너뜁니다 (run=%s)",
                claim.run_id,
            )


def main(
    argv: Sequence[str] | None = None,
    *,
    services: WorkflowWorkerServices,
    default_queue: str,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--queue",
        default=os.getenv("WORKFLOW_QUEUE", default_queue),
    )
    parser.add_argument(
        "--worker-id",
        default=os.getenv("KUBERNETES_JOB_NAME") or socket.gethostname(),
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    run_one(args.queue, args.worker_id, services=services)
    return 0


__all__ = [
    "ModuleTaskTimeout",
    "WorkflowWorkerServices",
    "execute_with_policy",
    "main",
    "run_one",
    "task_timeout",
]
