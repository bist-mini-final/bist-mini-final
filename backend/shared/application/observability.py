"""Correlation context shared by HTTP requests and background workers."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from typing import Iterator


@dataclass(frozen=True, slots=True)
class ObservabilityContext:
    """Identifiers that make one unit of work traceable across log boundaries."""

    request_id: str | None = None
    run_id: str | None = None
    job_id: str | None = None
    worker_id: str | None = None

    def log_extra(self) -> dict[str, str]:
        return {
            name: value
            for name, value in (
                ("request_id", self.request_id),
                ("run_id", self.run_id),
                ("job_id", self.job_id),
                ("worker_id", self.worker_id),
            )
            if value is not None
        }


_CONTEXT: ContextVar[ObservabilityContext | None] = ContextVar(
    "backend_observability_context",
    default=None,
)


def current_observability_context() -> ObservabilityContext:
    """Return the correlation identifiers bound to the current execution context."""

    return _CONTEXT.get() or ObservabilityContext()


@contextmanager
def bind_observability_context(
    *,
    request_id: str | None = None,
    run_id: str | None = None,
    job_id: str | None = None,
    worker_id: str | None = None,
) -> Iterator[ObservabilityContext]:
    """Merge identifiers for a scoped request, job, or worker execution."""

    current = current_observability_context()
    bound = replace(
        current,
        request_id=request_id if request_id is not None else current.request_id,
        run_id=run_id if run_id is not None else current.run_id,
        job_id=job_id if job_id is not None else current.job_id,
        worker_id=worker_id if worker_id is not None else current.worker_id,
    )
    token = _CONTEXT.set(bound)
    try:
        yield bound
    finally:
        _CONTEXT.reset(token)


def observability_log_extra() -> dict[str, str]:
    """Build a logging ``extra`` mapping for the current execution context."""

    return current_observability_context().log_extra()


__all__ = [
    "ObservabilityContext",
    "bind_observability_context",
    "current_observability_context",
    "observability_log_extra",
]
