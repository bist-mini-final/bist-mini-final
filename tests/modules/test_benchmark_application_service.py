from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from backend.domains.benchmark.application.execution import execute_benchmark_comparison
from backend.domains.benchmark.application.service import (
    BenchmarkApplicationService,
    BenchmarkQueueUnavailableError,
)
from backend.domains.benchmark.domain import BenchmarkCase, BenchmarkRequest
from backend.domains.workflow.domain import DagExecutionError
from backend.domains.workflow.infrastructure.job_catalog import canonical_workflow


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
        benchmark_sets=unused,
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


def test_benchmark_execution_preserves_failed_rows_and_progress_contract() -> None:
    workflow = canonical_workflow("rag_query")
    assert workflow is not None

    class Workflows:
        def load(self, workflow_id: str):
            return workflow.model_copy(update={"id": workflow_id})

    class Executor:
        def create_run(self, *_args, **_kwargs):
            raise DagExecutionError("worker unavailable")

    events: list[dict[str, Any]] = []
    request = BenchmarkRequest(
        workflow_ids=["rag-a", "rag-b"],
        cases=[BenchmarkCase(id="case-1", question="test", expected_terms=["answer"])],
    )

    result = execute_benchmark_comparison(
        request,
        cast(Any, Workflows()),
        cast(Any, Executor()),
        cast(Any, SimpleNamespace()),
        events.append,
    )

    assert len(result["results"]) == 2
    assert all(row["error"] == "worker unavailable" for row in result["results"])
    assert all(row["score"]["correct"] is False for row in result["results"])
    assert [event["event"] for event in events] == [
        "started",
        "completed",
        "started",
        "completed",
    ]
