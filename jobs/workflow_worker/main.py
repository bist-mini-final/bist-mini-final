"""Claim and execute exactly one PostgreSQL-queued workflow run."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from functools import lru_cache
import logging
import os
import signal
import socket
from threading import Event, Thread
import time
from typing import Iterator, Optional

from backend.core.settings import KUBERNETES_INGESTION_QUEUE
from backend.storage.data_sources import INGESTION_WORKFLOW_IDS
from backend.storage.data_sources.ingestion_registry import IngestionModuleRegistry
from backend.engine.orchestration import compile_task_plan
from backend.engine.runtime.services import (
    WorkflowRuntimeServices,
    create_workflow_runtime_services,
)
from backend.storage.answer_cache import AnswerCacheRepository
from backend.storage.db_manager import WorkflowRunAlreadyClaimed, WorkflowRunLease
from backend.engine.workflows.executor import DagExecutionCancelled

logger = logging.getLogger(__name__)


class ModuleTaskTimeout(TimeoutError):
    """Raised when one module exceeds its declared task timeout."""


@lru_cache(maxsize=1)
def runtime_services() -> WorkflowRuntimeServices:
    """Build the lean ingestion runtime once per one-shot Job pod."""

    return create_workflow_runtime_services(
        AnswerCacheRepository(),
        initialize_schema=False,
        require_database=True,
        registry_factory=IngestionModuleRegistry,
    )


@contextmanager
def task_timeout(seconds: Optional[float]) -> Iterator[None]:
    """Apply a per-module wall-clock timeout in the worker's main thread."""

    if seconds is None or not hasattr(signal, "setitimer"):
        yield
        return

    def _timeout_handler(_signum: int, _frame: object) -> None:
        raise ModuleTaskTimeout(f"모듈 실행 제한 시간 {seconds:g}초를 초과했습니다")

    previous_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def execute_with_policy(
    services: WorkflowRuntimeServices,
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


def _heartbeat_loop(
    services: WorkflowRuntimeServices,
    run_id: str,
    worker_id: str,
    lease_token: str,
    stop: Event,
    interval_seconds: float,
) -> None:
    while not stop.wait(interval_seconds):
        try:
            if not services.db_manager.heartbeat_workflow_run(
                run_id,
                worker_id,
                lease_token,
            ):
                return
        except Exception:
            logger.warning("워크플로 lease heartbeat 실패", exc_info=True)


def _execute_claim(
    services: WorkflowRuntimeServices,
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
        with services.db_manager.claim_workflow_run(
            run_id,
            queue_name=queue_name,
            worker_id=worker_id,
            lease_token=lease_token,
            stale_after_seconds=stale_after_seconds,
        ):
            with services.run_store.workflow_lease(run_id, lease_token):
                stop = Event()
                heartbeat = Thread(
                    target=_heartbeat_loop,
                    args=(
                        services,
                        run_id,
                        worker_id,
                        lease_token,
                        stop,
                        heartbeat_seconds,
                    ),
                    name="workflow-lease-heartbeat",
                    daemon=True,
                )
                heartbeat.start()
                try:
                    run = services.run_store.load(run_id)
                    if run.workflow_id not in INGESTION_WORKFLOW_IDS:
                        raise ValueError(
                            "이 큐가 처리할 수 없는 workflow입니다: "
                            f"{run.workflow_id}"
                        )
                    plan = compile_task_plan(run, services.module_registry)
                    for planned in plan:
                        policy = planned.policy
                        execute_with_policy(
                            services,
                            run_id,
                            planned.node_id,
                            policy.retries,
                            policy.retry_delay_seconds,
                            policy.timeout_seconds,
                        )
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
                    stop.set()
                    heartbeat.join(timeout=heartbeat_seconds + 1)
    except DagExecutionCancelled:
        logger.info("배치 run 취소 완료 (run=%s)", run_id)
        return run_id
    except WorkflowRunAlreadyClaimed:
        raise
    except Exception as error:
        try:
            services.db_manager.fail_workflow_run_claim(
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
    stale_after_seconds: int = 180,
    heartbeat_seconds: float = 15,
) -> Optional[str]:
    """Claim and finish one item; skip candidates still owned by another worker."""

    services = runtime_services()
    excluded_run_ids: list[str] = []
    while True:
        claim = services.db_manager.claim_next_workflow_run(
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--queue",
        default=os.getenv("WORKFLOW_QUEUE", KUBERNETES_INGESTION_QUEUE),
    )
    parser.add_argument(
        "--worker-id",
        default=os.getenv("KUBERNETES_JOB_NAME") or socket.gethostname(),
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    run_one(args.queue, args.worker_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
