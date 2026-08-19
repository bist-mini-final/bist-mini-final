from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException

from ..core.settings import CACHE_DIR, RUN_DIR, WORKFLOW_DIR
from ..runtime.registry import ModuleRegistry
from ..workflows import (
    DagExecutionCancelled,
    DagExecutionError,
    ResultCache,
    RunStore,
    WorkflowExecutionRequest,
    WorkflowExecutor,
    WorkflowRunDispatcher,
    WorkflowSaveRequest,
    WorkflowStore,
)


def create_workflow_router(
    module_registry: ModuleRegistry,
    workflow_dir: Optional[Path] = None,
    run_dir: Optional[Path] = None,
    cache_dir: Optional[Path] = None,
    workflow_store: Optional[WorkflowStore] = None,
    run_store: Optional[RunStore] = None,
    workflow_executor: Optional[WorkflowExecutor] = None,
    workflow_dispatcher: Optional[WorkflowRunDispatcher] = None,
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
    workflow_store = workflow_store or WorkflowStore(workflow_dir or WORKFLOW_DIR)
    run_store = run_store or RunStore(run_dir or RUN_DIR)
    workflow_executor = workflow_executor or WorkflowExecutor(
        module_registry,
        run_store,
        ResultCache(cache_dir or CACHE_DIR),
    )
    workflow_dispatcher = workflow_dispatcher or WorkflowRunDispatcher(
        workflow_executor,
        run_store,
    )

    @router.delete("/cache")
    def clear_runtime_cache():
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

    @router.post("/workflows/{workflow_id}/runs")
    def create_workflow_run(
        workflow_id: str,
        request: WorkflowExecutionRequest,
    ):
        try:
            workflow = workflow_store.load(workflow_id)
            return workflow_executor.create_run(workflow, request)
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404, detail=f"워크플로 {workflow_id}를 찾을 수 없습니다"
            ) from error
        except (DagExecutionError, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/workflows/{workflow_id}/execute")
    def execute_workflow(
        workflow_id: str,
        request: WorkflowExecutionRequest,
    ):
        try:
            workflow = workflow_store.load(workflow_id)
            run = workflow_executor.create_run(workflow, request)
            return workflow_executor.execute_all(run.id)
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404, detail=f"워크플로 {workflow_id}를 찾을 수 없습니다"
            ) from error
        except DagExecutionCancelled as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except (DagExecutionError, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.get("/runs")
    def list_runs(workflow_id: Optional[str] = None):
        return {"runs": run_store.list(workflow_id)}

    @router.get("/runs/{run_id}")
    def get_run(run_id: str):
        try:
            return run_store.load(run_id)
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404, detail=f"실행 {run_id}를 찾을 수 없습니다"
            ) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/runs/{run_id}/execute-next")
    def execute_next_batch(run_id: str):
        try:
            return workflow_executor.execute_next_batch(run_id)
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404, detail=f"실행 {run_id}를 찾을 수 없습니다"
            ) from error
        except DagExecutionCancelled as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except DagExecutionError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/runs/{run_id}/nodes/{node_id}/execute")
    def execute_single_node(run_id: str, node_id: str):
        try:
            return workflow_executor.execute_node(run_id, node_id)
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404, detail=f"실행 {run_id}를 찾을 수 없습니다"
            ) from error
        except DagExecutionCancelled as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except DagExecutionError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/runs/{run_id}/execute")
    def execute_remaining_batches(run_id: str):
        try:
            return workflow_executor.execute_all(run_id)
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404, detail=f"실행 {run_id}를 찾을 수 없습니다"
            ) from error
        except DagExecutionCancelled as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except DagExecutionError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/runs/{run_id}/resume")
    def resume_run(run_id: str):
        try:
            return workflow_executor.resume(run_id)
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404, detail=f"실행 {run_id}를 찾을 수 없습니다"
            ) from error
        except DagExecutionCancelled as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except DagExecutionError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/runs/{run_id}/cancel")
    def cancel_run(run_id: str):
        try:
            return workflow_dispatcher.cancel(run_id)
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404, detail=f"실행 {run_id}를 찾을 수 없습니다"
            ) from error

    return router
