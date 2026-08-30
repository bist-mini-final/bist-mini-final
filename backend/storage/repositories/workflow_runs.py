"""Composed compatibility facade for workflow persistence capabilities."""

from __future__ import annotations

from .workflow_history import WorkflowRunHistoryRepositoryMixin
from .workflow_queue import (
    WorkflowLeaseLost,
    WorkflowRunAlreadyClaimed,
    WorkflowRunLease,
    WorkflowRunQueueRepositoryMixin,
)
from .workflow_state import WorkflowRunStateRepositoryMixin


class WorkflowRunRepositoryMixin(
    WorkflowRunQueueRepositoryMixin,
    WorkflowRunStateRepositoryMixin,
    WorkflowRunHistoryRepositoryMixin,
):
    """Compose queue, current-state, and history persistence capabilities."""


__all__ = [
    "WorkflowLeaseLost",
    "WorkflowRunAlreadyClaimed",
    "WorkflowRunLease",
    "WorkflowRunRepositoryMixin",
]
