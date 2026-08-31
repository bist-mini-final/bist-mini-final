"""Ports consumed by benchmark application and worker use cases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from backend.domains.benchmark.domain import ClaimedBenchmarkJob


@dataclass(frozen=True, slots=True)
class BenchmarkStoreError(RuntimeError):
    operation: str
    reason: str

    def __str__(self) -> str:
        return f"benchmark PostgreSQL store {self.operation} failed: {self.reason}"


@dataclass(frozen=True)
class BenchmarkSetDocument:
    set_id: str
    name: str
    cases: tuple[dict[str, Any], ...]


class BenchmarkSetSourceError(RuntimeError):
    pass


class BenchmarkSetSourcePort(Protocol):
    def list_documents(self) -> tuple[BenchmarkSetDocument, ...]: ...


class BenchmarkStorePort(Protocol):
    def enqueue(
        self,
        job_id: str,
        request_payload: dict[str, Any],
        total: int,
        created_at: datetime,
    ) -> dict[str, Any]: ...

    def get(self, job_id: str) -> dict[str, Any] | None: ...
    def request_cancel(self, job_id: str) -> dict[str, Any] | None: ...
    def request_pause(self, job_id: str) -> dict[str, Any] | None: ...
    def request_resume(self, job_id: str) -> dict[str, Any] | None: ...
    def list_results(self, limit: int = 50) -> list[dict[str, Any]]: ...
    def get_result(self, benchmark_id: str) -> dict[str, Any] | None: ...


class BenchmarkWorkerStorePort(Protocol):
    def claim_next(
        self,
        worker_id: str,
        claimed_at: datetime,
        *,
        stale_after_seconds: int = 180,
    ) -> ClaimedBenchmarkJob | None: ...

    def heartbeat(self, job_id: str, worker_id: str) -> bool: ...
    def control(self, job_id: str, worker_id: str) -> tuple[bool, bool]: ...
    def mark_paused(self, job_id: str, worker_id: str) -> bool: ...
    def mark_running(self, job_id: str, worker_id: str) -> bool: ...
    def update_progress(
        self,
        job_id: str,
        worker_id: str,
        progress: dict[str, Any],
    ) -> bool: ...
    def finish_completed(
        self,
        job_id: str,
        worker_id: str,
        result: dict[str, Any],
        completed_at: datetime,
    ) -> bool: ...
    def finish_cancelled(
        self,
        job_id: str,
        worker_id: str,
        completed_at: datetime,
    ) -> bool: ...
    def finish_failed(
        self,
        job_id: str,
        worker_id: str,
        error_message: str,
        completed_at: datetime,
    ) -> bool: ...


class BenchmarkRunStorePort(Protocol):
    def load_summary(self, run_id: str) -> Any: ...


__all__ = [
    "BenchmarkRunStorePort",
    "BenchmarkSetDocument",
    "BenchmarkSetSourceError",
    "BenchmarkSetSourcePort",
    "BenchmarkStoreError",
    "BenchmarkStorePort",
    "BenchmarkWorkerStorePort",
]
