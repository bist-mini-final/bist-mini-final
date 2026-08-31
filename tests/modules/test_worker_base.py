from __future__ import annotations

import logging
from dataclasses import dataclass

from backend.shared.application.observability import (
    ObservabilityContext,
    bind_observability_context,
    current_observability_context,
)
from backend.shared.application.workers import LeasedWorker, WorkerLeaseSpec


@dataclass(frozen=True, slots=True)
class _Claim:
    job_id: str


class _Worker(LeasedWorker[_Claim, str]):
    def __init__(self, *, claim: _Claim | None, failure: Exception | None = None) -> None:
        super().__init__(logging.getLogger(__name__))
        self._next_claim = claim
        self._failure = failure
        self.context_during_execute: ObservabilityContext | None = None
        self.completed: tuple[_Claim, str] | None = None
        self.failed: tuple[_Claim, Exception] | None = None

    def claim(self) -> _Claim | None:
        return self._next_claim

    def lease_spec(self, claim: _Claim) -> WorkerLeaseSpec:
        return WorkerLeaseSpec(
            job_id=claim.job_id,
            run_id="run-1",
            worker_id="worker-1",
            renew=lambda: True,
            thread_name="test-worker-heartbeat",
            failure_message="test worker heartbeat failed",
            interval_seconds=60,
            on_lease_lost=None,
        )

    def execute(self, claim: _Claim) -> str:
        self.context_during_execute = current_observability_context()
        if self._failure is not None:
            raise self._failure
        return f"done:{claim.job_id}"

    def complete(
        self,
        claim: _Claim,
        output: str,
        duration_seconds: float,
    ) -> None:
        self.completed = (claim, output)

    def fail(
        self,
        claim: _Claim,
        error: Exception,
        duration_seconds: float,
    ) -> None:
        self.failed = (claim, error)


def test_leased_worker_owns_success_lifecycle_and_correlation_context() -> None:
    worker = _Worker(claim=_Claim("job-1"))

    assert worker.run_once() == 0

    assert worker.completed == (_Claim("job-1"), "done:job-1")
    assert worker.failed is None
    assert worker.context_during_execute == ObservabilityContext(
        run_id="run-1",
        job_id="job-1",
        worker_id="worker-1",
    )
    assert current_observability_context() == ObservabilityContext()


def test_leased_worker_persists_failure_without_leaking_context() -> None:
    failure = RuntimeError("broken")
    worker = _Worker(claim=_Claim("job-2"), failure=failure)

    with bind_observability_context(request_id="request-1"):
        assert worker.run_once() == 1
        assert current_observability_context().request_id == "request-1"

    assert worker.completed is None
    assert worker.failed == (_Claim("job-2"), failure)
    assert worker.context_during_execute == ObservabilityContext(
        request_id="request-1",
        run_id="run-1",
        job_id="job-2",
        worker_id="worker-1",
    )
    assert current_observability_context() == ObservabilityContext()


def test_leased_worker_returns_success_when_queue_is_empty() -> None:
    worker = _Worker(claim=None)

    assert worker.run_once() == 0
    assert worker.completed is None
    assert worker.failed is None
