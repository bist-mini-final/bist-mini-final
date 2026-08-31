"""Workflow HTTP error mapping and SSE event presentation."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from anyio import to_thread
from fastapi import HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from backend.domains.workflow.application.execution_service import ActiveWorkflowRunsError
from backend.domains.workflow.application.services import (
    WorkflowCommandService,
    WorkflowQueryService,
)
from backend.domains.workflow.domain import DagExecutionError
from backend.domains.workflow.domain.models import (
    RunNodeState,
    WorkflowDocument,
    WorkflowExecutionRequest,
    WorkflowRun,
    WorkflowSaveRequest,
)
from backend.shared.application.state_stream import SharedStateStream


def _queue_unavailable(error: RuntimeError, **context: str) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "WORKFLOW_QUEUE_UNAVAILABLE",
            "message": str(error),
            "retryable": True,
            "context": context,
        },
    )


def _node_fingerprint(node: RunNodeState) -> tuple[object, ...]:
    return (
        node.status,
        node.elapsed_ms,
        node.error,
        json.dumps(node.progress, sort_keys=True, default=str),
    )


def _node_event_name(status: str) -> str:
    if status in ("succeeded", "skipped"):
        return "node_completed"
    if status == "failed":
        return "node_failed"
    if status == "running":
        return "node_started"
    return "node_progress"


def _run_started_event(run: WorkflowRun) -> dict[str, str]:
    return {
        "event": "run_started",
        "data": json.dumps(
            {
                "run_id": run.id,
                "workflow_id": run.workflow_id,
                "status": run.status,
                "batches_count": len(run.batches),
                "nodes_count": len(run.nodes),
            },
            ensure_ascii=False,
        ),
    }


def _node_event(node: RunNodeState) -> dict[str, str]:
    return {
        "event": _node_event_name(node.status),
        "data": json.dumps(node.model_dump(mode="json"), ensure_ascii=False),
    }


def _run_terminal_event(run: WorkflowRun) -> dict[str, str]:
    return {
        "event": "run_finished" if run.status == "completed" else "run_failed",
        "data": json.dumps(
            {
                "run_id": run.id,
                "status": run.status,
                "run": run.model_dump(mode="json"),
            },
            ensure_ascii=False,
        ),
    }


async def workflow_run_events(
    stream: SharedStateStream[str, WorkflowRun],
    run_id: str,
    initial: WorkflowRun,
    request: Request,
) -> AsyncIterator[dict[str, str]]:
    """Translate persisted workflow states into stable public SSE events."""

    previous_nodes: dict[str, tuple[object, ...]] = {}
    started = False
    try:
        async for run in stream.subscribe(run_id, initial=initial):
            if await request.is_disconnected():
                return
            if not started:
                started = True
                yield _run_started_event(run)
            for node_id, node in run.nodes.items():
                fingerprint = _node_fingerprint(node)
                if previous_nodes.get(node_id) == fingerprint:
                    continue
                previous_nodes[node_id] = fingerprint
                yield _node_event(node)
            if run.status in ("completed", "failed", "paused"):
                yield _run_terminal_event(run)
                return
    except Exception as error:
        yield {
            "event": "error",
            "data": json.dumps(
                {"error": str(error), "run_id": run_id},
                ensure_ascii=False,
            ),
        }


class WorkflowHttpController:
    """Map application outcomes to the existing workflow HTTP contract."""

    def __init__(
        self,
        commands: WorkflowCommandService,
        queries: WorkflowQueryService,
        run_stream: SharedStateStream[str, WorkflowRun],
    ) -> None:
        self._commands = commands
        self._queries = queries
        self._run_stream = run_stream

    def clear_runtime_cache(self) -> dict[str, Any]:
        try:
            return self._commands.clear_runtime_cache()
        except ActiveWorkflowRunsError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    def list_workflows(self) -> dict[str, Any]:
        return {"workflows": self._queries.list_workflows()}

    def get_workflow(self, workflow_id: str) -> WorkflowDocument:
        try:
            return self._queries.get_workflow(workflow_id)
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail=f"워크플로 {workflow_id}를 찾을 수 없습니다.",
            ) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    def save_workflow(
        self,
        workflow_id: str,
        request: WorkflowSaveRequest | None,
    ) -> WorkflowDocument:
        if request is None:
            raise HTTPException(status_code=422, detail="요청 본문이 필요합니다.")
        try:
            return self._commands.save_workflow(workflow_id, request)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    def delete_workflow(self, workflow_id: str) -> dict[str, str]:
        try:
            return {"deleted": self._commands.delete_workflow(workflow_id)}
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail=f"워크플로를 찾을 수 없습니다: {workflow_id}",
            ) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    def submit_run(
        self,
        workflow_id: str,
        request: WorkflowExecutionRequest | None,
    ) -> WorkflowRun:
        if request is None:
            raise HTTPException(status_code=422, detail="요청 본문이 필요합니다.")
        try:
            return self._commands.submit_run(workflow_id, request)
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail=f"워크플로 {workflow_id}를 찾을 수 없습니다.",
            ) from error
        except (DagExecutionError, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except RuntimeError as error:
            raise _queue_unavailable(error, workflow_id=workflow_id) from error

    def list_runs(
        self,
        workflow_id: str | None,
        limit: int,
    ) -> dict[str, Any]:
        return {"runs": self._queries.list_runs(workflow_id, limit)}

    def get_run(self, run_id: str) -> WorkflowRun:
        try:
            return self._queries.get_run(run_id)
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail=f"실행 {run_id}를 찾을 수 없습니다.",
            ) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    def get_run_node(self, run_id: str, node_id: str) -> RunNodeState:
        try:
            return self._queries.get_run_node(run_id, node_id)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    def resume_run(self, run_id: str) -> WorkflowRun:
        try:
            return self._commands.resume_run(run_id)
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail=f"실행 {run_id}를 찾을 수 없습니다.",
            ) from error
        except DagExecutionError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except RuntimeError as error:
            raise _queue_unavailable(error, run_id=run_id) from error

    def cancel_run(self, run_id: str) -> WorkflowRun:
        try:
            return self._commands.cancel_run(run_id)
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail=f"실행 {run_id}를 찾을 수 없습니다.",
            ) from error
        except RuntimeError as error:
            raise _queue_unavailable(error, run_id=run_id) from error

    async def stream_run(self, run_id: str, request: Request) -> EventSourceResponse:
        try:
            initial = await to_thread.run_sync(self._queries.get_run, run_id)
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail=f"실행 {run_id}를 찾을 수 없습니다.",
            ) from error
        except RuntimeError as error:
            raise _queue_unavailable(error, run_id=run_id) from error
        return EventSourceResponse(
            workflow_run_events(self._run_stream, run_id, initial, request),
            ping=15,
        )


__all__ = ["WorkflowHttpController", "workflow_run_events"]
