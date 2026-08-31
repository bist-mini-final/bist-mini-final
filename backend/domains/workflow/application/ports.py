"""Ports required by the workflow application service."""

from __future__ import annotations

from typing import Any, Protocol

from backend.domains.workflow.domain.models import (
    RunNodeState,
    WorkflowDocument,
    WorkflowExecutionRequest,
    WorkflowRun,
    WorkflowSaveRequest,
)


class WorkflowDefinitionRepository(Protocol):
    def list(self) -> list[WorkflowDocument]: ...

    def load(self, workflow_id: str) -> WorkflowDocument: ...

    def save(
        self,
        workflow_id: str,
        request: WorkflowSaveRequest,
    ) -> WorkflowDocument: ...

    def delete(self, workflow_id: str) -> None: ...


class WorkflowRunRepository(Protocol):
    @property
    def supports_durable_queue(self) -> bool: ...

    def load(self, run_id: str) -> WorkflowRun: ...

    def load_summary(self, run_id: str) -> WorkflowRun: ...

    def load_node(self, run_id: str, node_id: str) -> RunNodeState: ...

    def list(
        self,
        workflow_id: str | None = None,
        limit: int | None = None,
    ) -> list[WorkflowRun]: ...

    def save(self, run: WorkflowRun) -> WorkflowRun: ...

    def save_node(self, run: WorkflowRun, node_id: str) -> WorkflowRun: ...

    def save_progress(self, run: WorkflowRun, node_id: str) -> WorkflowRun: ...

    def is_cancel_requested(self, run_id: str) -> bool: ...

    def clear_cancel_request(self, run_id: str) -> None: ...

    def clear(self) -> int: ...


class WorkflowExecutorPort(Protocol):
    def create_run(
        self,
        workflow: WorkflowDocument,
        request: WorkflowExecutionRequest,
    ) -> WorkflowRun: ...

    def clear_runtime_cache(self) -> dict[str, int]: ...


class WorkflowResultCache(Protocol):
    @staticmethod
    def key(module_type: str, payload: Any) -> str: ...

    def get(self, cache_key: str) -> Any: ...

    def put(self, cache_key: str, value: Any) -> None: ...

    def clear(self) -> int: ...


__all__ = [
    "WorkflowDefinitionRepository",
    "WorkflowExecutorPort",
    "WorkflowResultCache",
    "WorkflowRunRepository",
]
