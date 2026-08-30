"""Workflow command/query boundaries consumed by presentation adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from backend.engine.workflows.models import (
    RunNodeState,
    WorkflowDocument,
    WorkflowExecutionRequest,
    WorkflowRun,
    WorkflowSaveRequest,
)
from backend.engine.workflows.service import WorkflowExecutionPort


class WorkflowDefinitionStorePort(Protocol):
    def list(self) -> list[WorkflowDocument]: ...

    def load(self, workflow_id: str) -> WorkflowDocument: ...

    def save(
        self,
        workflow_id: str,
        request: WorkflowSaveRequest,
    ) -> WorkflowDocument: ...

    def delete(self, workflow_id: str) -> None: ...


class WorkflowRunQueryPort(Protocol):
    def list(
        self,
        workflow_id: str | None = None,
        limit: int | None = None,
    ) -> list[WorkflowRun]: ...

    def load_summary(self, run_id: str) -> WorkflowRun: ...

    def load_node(self, run_id: str, node_id: str) -> RunNodeState: ...


@dataclass(frozen=True, slots=True)
class WorkflowQueryService:
    definitions: WorkflowDefinitionStorePort
    runs: WorkflowRunQueryPort

    def list_workflows(self) -> list[WorkflowDocument]:
        return self.definitions.list()

    def get_workflow(self, workflow_id: str) -> WorkflowDocument:
        return self.definitions.load(workflow_id)

    def list_runs(
        self,
        workflow_id: str | None,
        limit: int,
    ) -> list[WorkflowRun]:
        return self.runs.list(workflow_id, limit)

    def get_run(self, run_id: str) -> WorkflowRun:
        return self.runs.load_summary(run_id)

    def get_run_node(self, run_id: str, node_id: str) -> RunNodeState:
        return self.runs.load_node(run_id, node_id)


@dataclass(frozen=True, slots=True)
class WorkflowCommandService:
    definitions: WorkflowDefinitionStorePort
    execution: WorkflowExecutionPort

    def clear_runtime_cache(self) -> dict[str, Any]:
        return self.execution.clear_runtime_cache()

    def save_workflow(
        self,
        workflow_id: str,
        request: WorkflowSaveRequest,
    ) -> WorkflowDocument:
        return self.definitions.save(workflow_id, request)

    def delete_workflow(self, workflow_id: str) -> str:
        self.definitions.delete(workflow_id)
        return workflow_id

    def submit_run(
        self,
        workflow_id: str,
        request: WorkflowExecutionRequest,
    ) -> WorkflowRun:
        return self.execution.submit(workflow_id, request)

    def resume_run(self, run_id: str) -> WorkflowRun:
        return self.execution.resume(run_id)

    def cancel_run(self, run_id: str) -> WorkflowRun:
        return self.execution.cancel(run_id)


__all__ = [
    "WorkflowCommandService",
    "WorkflowDefinitionStorePort",
    "WorkflowQueryService",
    "WorkflowRunQueryPort",
]
