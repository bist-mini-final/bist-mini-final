import json
from typing import Optional

from anyio import to_thread
from fastapi import APIRouter, HTTPException, Query, Request
from sse_starlette.sse import EventSourceResponse

from backend.core.state_stream import SharedStateStream
from backend.engine.workflows import (
    DagExecutionError,
    RunDispatcher,
    RunStore,
    WorkflowExecutionRequest,
    WorkflowExecutor,
    WorkflowSaveRequest,
    WorkflowStore,
)


def create_workflow_router(
    *,
    workflow_store: WorkflowStore,
    run_store: RunStore,
    workflow_executor: WorkflowExecutor,
    workflow_dispatcher: RunDispatcher,
) -> APIRouter:
    """
    Build a FastAPI router for workflow storage and run execution.
    
    Parameters:
        module_registry (ModuleRegistry): Registry used to resolve workflow modules.
        workflow_dir (Path): Directory containing workflow data.
        run_dir (Path): Directory containing run data.
        cache_dir (Path): Directory used for runtime cache data.
        workflow_store (Optional[WorkflowStore]): Workflow store to use, or a default store when omitted.
        run_store (Optional[RunStore]): Run store to use, or a default store when omitted.
        workflow_executor (Optional[WorkflowExecutor]): Executor to use, or a default executor when omitted.
    
    Returns:
        APIRouter: Configured router for workflow and run management.
    """
    router = APIRouter(tags=["Workflows"])
    run_stream = SharedStateStream(
        run_store.load_summary,
        fingerprint=lambda run: run.updated_at,
        terminal=lambda run: run.status in ("completed", "failed", "paused"),
    )

    @router.delete("/cache")
    def clear_runtime_cache():
        workflow_dispatcher.cancel_all()
        if any(
            workflow_dispatcher.is_active(run.id)
            for run in run_store.list()
        ):
            raise HTTPException(
                status_code=409,
                detail="실행 중인 워크플로가 완전히 중지될 때까지 캐시를 삭제할 수 없습니다",
            )
        return workflow_executor.clear_runtime_cache()

    @router.get("/workflows")
    def list_workflows():
        return {"workflows": workflow_store.list()}

    @router.get("/workflows/{workflow_id}")
    def get_workflow(workflow_id: str):
        try:
            return workflow_store.load(workflow_id)
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404, detail=f"워크플로 {workflow_id}를 찾을 수 없습니다"
            ) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.put("/workflows/{workflow_id}")
    def save_workflow(workflow_id: str, request: WorkflowSaveRequest):
        try:
            return workflow_store.save(workflow_id, request)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.delete("/workflows/{workflow_id}")
    def delete_workflow(workflow_id: str):
        try:
            workflow_store.delete(workflow_id)
            return {"deleted": workflow_id}
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}") from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/workflows/{workflow_id}/runs", status_code=202)
    def create_workflow_run(
        workflow_id: str,
        request: WorkflowExecutionRequest,
    ):
        try:
            if run_store.db_manager is None:
                raise RuntimeError(
                    "Kubernetes workflow 제출에는 PostgreSQL 연결이 필요합니다"
                )
            workflow = workflow_store.load(workflow_id)
            run = workflow_executor.create_run(workflow, request)
            workflow_dispatcher.submit(run.id)
            return run_store.load_summary(run.id)
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404, detail=f"워크플로 {workflow_id}를 찾을 수 없습니다"
            ) from error
        except (DagExecutionError, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "WORKFLOW_QUEUE_UNAVAILABLE",
                    "message": str(error),
                    "retryable": True,
                    "context": {"workflow_id": workflow_id},
                },
            ) from error

    @router.get("/runs")
    def list_runs(
        workflow_id: Optional[str] = None,
        limit: int = Query(default=50, ge=1, le=200),
    ):
        return {"runs": run_store.list(workflow_id, limit)}

    @router.get("/runs/{run_id}")
    def get_run(run_id: str):
        try:
            return run_store.load_summary(run_id)
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404, detail=f"실행 {run_id}를 찾을 수 없습니다"
            ) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/runs/{run_id}/resume")
    def resume_run(run_id: str):
        try:
            workflow_dispatcher.submit(run_id, resume_failed=True)
            return run_store.load_summary(run_id)
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404, detail=f"실행 {run_id}를 찾을 수 없습니다"
            ) from error
        except DagExecutionError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "WORKFLOW_QUEUE_UNAVAILABLE",
                    "message": str(error),
                    "retryable": True,
                    "context": {"run_id": run_id},
                },
            ) from error

    @router.post("/runs/{run_id}/cancel")
    def cancel_run(run_id: str):
        try:
            return workflow_dispatcher.cancel(run_id)
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404, detail=f"실행 {run_id}를 찾을 수 없습니다"
            ) from error
        except RuntimeError as error:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "WORKFLOW_QUEUE_UNAVAILABLE",
                    "message": str(error),
                    "retryable": True,
                    "context": {"run_id": run_id},
                },
            ) from error

    @router.get("/runs/{run_id}/stream")
    async def stream_workflow_run(run_id: str, request: Request):
        """Observe a Kubernetes-owned run without executing work in the API."""
        try:
            initial_run = await to_thread.run_sync(run_store.load_summary, run_id)
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404, detail=f"실행 {run_id}를 찾을 수 없습니다"
            ) from error
        except RuntimeError as error:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "WORKFLOW_QUEUE_UNAVAILABLE",
                    "message": str(error),
                    "retryable": True,
                    "context": {"run_id": run_id},
                },
            ) from error

        async def event_generator():
            previous_node_statuses: dict[str, tuple[object, ...]] = {}
            started = False
            try:
                async for run in run_stream.subscribe(run_id, initial=initial_run):
                    if await request.is_disconnected():
                        break
                    if not started:
                        started = True
                        yield {
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
                    for node_id, node in run.nodes.items():
                        fingerprint = (
                            node.status,
                            node.elapsed_ms,
                            node.error,
                            json.dumps(node.progress, sort_keys=True, default=str),
                        )
                        if previous_node_statuses.get(node_id) == fingerprint:
                            continue
                        previous_node_statuses[node_id] = fingerprint
                        yield {
                            "event": (
                                "node_completed"
                                if node.status in ("succeeded", "skipped")
                                else "node_failed"
                                if node.status == "failed"
                                else "node_progress"
                            ),
                            "data": json.dumps(
                                node.model_dump(mode="json"),
                                ensure_ascii=False,
                            ),
                        }
                    if run.status in ("completed", "failed", "paused"):
                        yield {
                            "event": "run_completed",
                            "data": json.dumps(
                                {
                                    "run_id": run.id,
                                    "status": run.status,
                                    "run": run.model_dump(mode="json"),
                                },
                                ensure_ascii=False,
                            ),
                        }
                        break
            except Exception as error:
                yield {
                    "event": "error",
                    "data": json.dumps({"error": str(error), "run_id": run_id}, ensure_ascii=False),
                }

        return EventSourceResponse(event_generator())

    return router
