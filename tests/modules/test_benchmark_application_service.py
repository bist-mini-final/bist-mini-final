from __future__ import annotations

from typing import Any, cast

import pytest

from backend.domains.benchmark.application.service import (
    BenchmarkApplicationService,
    BenchmarkQueueUnavailableError,
)
from backend.features.benchmark.service import BenchmarkCase, BenchmarkRequest


class BenchmarkStore:
    def __init__(self, job: dict[str, Any]) -> None:
        self.job = job

    def get(self, job_id: str) -> dict[str, Any]:
        del job_id
        return dict(self.job)

    def request_cancel(self, job_id: str) -> dict[str, Any]:
        del job_id
        return {**self.job, "status": "cancelling"}

    def request_pause(self, job_id: str) -> dict[str, Any]:
        del job_id
        return {**self.job, "status": "pausing"}

    def request_resume(self, job_id: str) -> dict[str, Any]:
        del job_id
        return {**self.job, "status": "queued"}


class WorkflowExecution:
    def __init__(self) -> None:
        self.cancelled: list[str] = []

    def cancel(self, run_id: str) -> None:
        self.cancelled.append(run_id)


def application(
    store: BenchmarkStore,
    execution: WorkflowExecution,
    *,
    queue_available: bool = True,
) -> BenchmarkApplicationService:
    unused = cast(Any, object())
    return BenchmarkApplicationService(
        store=cast(Any, store),
        workflow_store=unused,
        run_store=unused,
        workflow_execution=cast(Any, execution),
        queue_available=queue_available,
    )


def test_start_job_rejects_missing_durable_queue_before_validation() -> None:
    service = application(
        BenchmarkStore({}),
        WorkflowExecution(),
        queue_available=False,
    )
    request = BenchmarkRequest(
        workflow_ids=["rag-a", "rag-b"],
        cases=[BenchmarkCase(id="case-1", question="test")],
    )

    with pytest.raises(BenchmarkQueueUnavailableError, match="PostgreSQL"):
        service.start_job(request)


def test_cancel_job_cancels_the_active_workflow_run() -> None:
    execution = WorkflowExecution()
    service = application(
        BenchmarkStore(
            {
                "id": "benchmark-job-1",
                "status": "running",
                "active_run_id": "run-1",
            }
        ),
        execution,
    )

    result = service.cancel_job("benchmark-job-1")

    assert result == {"id": "benchmark-job-1", "status": "cancelling"}
    assert execution.cancelled == ["run-1"]
