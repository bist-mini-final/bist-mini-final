"""Ports required by the workflow application service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from backend.engine.workflows.models import WorkflowRun


class WorkflowRunRepository(Protocol):
    def load(self, run_id: str) -> WorkflowRun: ...

    def load_summary(self, run_id: str) -> WorkflowRun: ...

    def save(self, run: WorkflowRun) -> WorkflowRun: ...

    def save_node(self, run: WorkflowRun, node_id: str) -> WorkflowRun: ...

    def save_progress(self, run: WorkflowRun, node_id: str) -> WorkflowRun: ...

    def is_cancel_requested(self, run_id: str) -> bool: ...

    def clear_cancel_request(self, run_id: str) -> None: ...

    def clear(self) -> int: ...


class WorkflowResultCache(Protocol):
    @staticmethod
    def key(module_type: str, payload: Any) -> str: ...

    def get(self, cache_key: str) -> Any: ...

    def put(self, cache_key: str, value: Any) -> None: ...

    def clear(self) -> int: ...


__all__ = ["WorkflowResultCache", "WorkflowRunRepository"]
