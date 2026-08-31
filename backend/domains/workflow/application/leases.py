"""Durable workflow queue lease contracts shared by workers and adapters."""

from __future__ import annotations

from dataclasses import dataclass


class WorkflowRunAlreadyClaimed(RuntimeError):
    """Raised when another database-connected worker owns the same run."""


class WorkflowLeaseLost(RuntimeError):
    """Raised when a worker persists with an obsolete lease token."""


@dataclass(frozen=True)
class WorkflowRunLease:
    """A single claim generation shared by every persistence operation."""

    run_id: str
    token: str


__all__ = ["WorkflowLeaseLost", "WorkflowRunAlreadyClaimed", "WorkflowRunLease"]
