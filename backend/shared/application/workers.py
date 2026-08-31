"""Template-method base class for one-shot leased workers."""

from __future__ import annotations

import logging
import os
import socket
from abc import ABC, abstractmethod
from dataclasses import dataclass
from time import perf_counter
from typing import Callable, Generic, TypeVar
from uuid import uuid4

from backend.shared.application.observability import (
    bind_observability_context,
    observability_log_extra,
)

from .leases import LeaseHeartbeat, LeaseLostError, terminate_process_on_lease_loss

ClaimT = TypeVar("ClaimT")
OutputT = TypeVar("OutputT")


def default_worker_id() -> str:
    """Return the Kubernetes Job name or a collision-resistant local identity."""

    return os.getenv("KUBERNETES_JOB_NAME") or (
        f"{socket.gethostname()}-{uuid4().hex[:12]}"
    )


@dataclass(frozen=True, slots=True)
class WorkerLeaseSpec:
    """Infrastructure-neutral description of a claimed worker lease."""

    job_id: str
    worker_id: str
    renew: Callable[[], bool]
    thread_name: str
    failure_message: str
    run_id: str | None = None
    interval_seconds: float = 30.0
    on_lease_lost: Callable[[LeaseLostError], None] | None = (
        terminate_process_on_lease_loss
    )


class LeasedWorker(ABC, Generic[ClaimT, OutputT]):
    """Own the invariant lifecycle shared by one-shot queue workers.

    Subclasses only define queue-specific claim, execution, and terminal state
    operations. Heartbeat ownership, correlation context, duration measurement,
    and failure containment stay identical across worker types.
    """

    def __init__(self, logger: logging.Logger) -> None:
        self._worker_logger = logger

    @abstractmethod
    def claim(self) -> ClaimT | None:
        """Claim the next available unit of work."""

    @abstractmethod
    def lease_spec(self, claim: ClaimT) -> WorkerLeaseSpec:
        """Describe how ownership of the claim is renewed."""

    @abstractmethod
    def execute(self, claim: ClaimT) -> OutputT:
        """Execute the claimed unit without applying terminal persistence."""

    @abstractmethod
    def complete(
        self,
        claim: ClaimT,
        output: OutputT,
        duration_seconds: float,
    ) -> None:
        """Persist successful terminal state while the lease is still owned."""

    @abstractmethod
    def fail(
        self,
        claim: ClaimT,
        error: Exception,
        duration_seconds: float,
    ) -> None:
        """Persist failed or retryable terminal state."""

    def empty_message(self) -> str:
        return f"{type(self).__name__}: claim 가능한 작업이 없습니다"

    def completed_message(self, claim: ClaimT, output: OutputT) -> str:
        return f"{type(self).__name__}: 작업 완료"

    def failed_message(self, claim: ClaimT, error: Exception) -> str:
        return f"{type(self).__name__}: 작업 실패"

    def run_once(self) -> int:
        """Claim and execute at most one item, returning a process exit code."""

        claim = self.claim()
        if claim is None:
            self._worker_logger.info(self.empty_message())
            return 0

        spec = self.lease_spec(claim)
        started = perf_counter()
        with bind_observability_context(
            job_id=spec.job_id,
            run_id=spec.run_id,
            worker_id=spec.worker_id,
        ):
            heartbeat = LeaseHeartbeat(
                spec.renew,
                interval_seconds=spec.interval_seconds,
                thread_name=spec.thread_name,
                logger=self._worker_logger,
                failure_message=spec.failure_message,
                on_lease_lost=spec.on_lease_lost,
            )
            heartbeat.start()
            try:
                output = self.execute(claim)
                heartbeat.raise_if_lost()
                self.complete(
                    claim,
                    output,
                    round(perf_counter() - started, 3),
                )
                self._worker_logger.info(
                    self.completed_message(claim, output),
                    extra=observability_log_extra(),
                )
                return 0
            except Exception as error:
                duration_seconds = round(perf_counter() - started, 3)
                self._worker_logger.exception(
                    self.failed_message(claim, error),
                    extra=observability_log_extra(),
                )
                try:
                    self.fail(claim, error, duration_seconds)
                except Exception:
                    self._worker_logger.exception(
                        "%s: 실패 상태 저장 실패",
                        type(self).__name__,
                        extra=observability_log_extra(),
                    )
                return 1
            finally:
                heartbeat.stop()


__all__ = ["LeasedWorker", "WorkerLeaseSpec", "default_worker_id"]
