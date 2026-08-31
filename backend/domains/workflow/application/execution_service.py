"""Application service for workflow execution commands.

HTTP adapters submit intent through this port and no longer decide whether to
touch the executor, durable run store, or Kubernetes dispatcher themselves.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from backend.domains.workflow.domain.models import WorkflowExecutionRequest, WorkflowRun

from .dispatching import RunDispatcher
from .ports import WorkflowDefinitionRepository, WorkflowExecutorPort, WorkflowRunRepository


class ActiveWorkflowRunsError(RuntimeError):
    """Raised when destructive cache cleanup races with an active run."""


class WorkflowExecutionPort(Protocol):
    """Use-case boundary consumed by HTTP and other control-plane adapters."""

    def submit(
        self,
        workflow_id: str,
        request: WorkflowExecutionRequest,
    ) -> WorkflowRun: ...

    def resume(self, run_id: str) -> WorkflowRun: ...

    def cancel(self, run_id: str) -> WorkflowRun: ...

    def clear_runtime_cache(self) -> dict[str, Any]: ...


@dataclass(slots=True)
class WorkflowExecutionService:
    workflow_store: WorkflowDefinitionRepository
    run_store: WorkflowRunRepository
    executor: WorkflowExecutorPort
    dispatcher: RunDispatcher

    def submit(
        self,
        workflow_id: str,
        request: WorkflowExecutionRequest,
    ) -> WorkflowRun:
        if not self.run_store.supports_durable_queue:
            raise RuntimeError(
                "Kubernetes workflow 제출에는 PostgreSQL 연결이 필요합니다."
            )
        workflow = self.workflow_store.load(workflow_id)
        run = self.executor.create_run(workflow, request)
        self.dispatcher.submit(run.id)
        return self.run_store.load_summary(run.id)

    def resume(self, run_id: str) -> WorkflowRun:
        self.dispatcher.submit(run_id, resume_failed=True)
        return self.run_store.load_summary(run_id)

    def cancel(self, run_id: str) -> WorkflowRun:
        return self.dispatcher.cancel(run_id)

    def clear_runtime_cache(self) -> dict[str, Any]:
        self.dispatcher.cancel_all()
        if any(self.dispatcher.is_active(run.id) for run in self.run_store.list()):
            raise ActiveWorkflowRunsError(
                "실행 중인 워크플로가 완전히 중지될 때까지 캐시를 삭제할 수 없습니다."
            )
        return self.executor.clear_runtime_cache()


__all__ = [
    "ActiveWorkflowRunsError",
    "WorkflowExecutionPort",
    "WorkflowExecutionService",
]
