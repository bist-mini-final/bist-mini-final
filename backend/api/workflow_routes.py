from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException

from ..runtime.registry import ModuleRegistry
from ..workflows import (
    DagExecutionCancelled,
    DagExecutionError,
    ResultCache,
    RunStore,
    WorkflowExecutionRequest,
    WorkflowExecutor,
    WorkflowSaveRequest,
    WorkflowStore,
)
from .benchmark_routes import create_benchmark_router


def create_workflow_router(
    module_registry: ModuleRegistry,
    workflow_dir: Path,
    run_dir: Path,
    cache_dir: Path,
) -> APIRouter:
    router = APIRouter(tags=["Workflows"])
    workflow_store = WorkflowStore(workflow_dir)
    run_store = RunStore(run_dir)
    result_cache = ResultCache(cache_dir)
    workflow_executor = WorkflowExecutor(
        module_registry,
        run_store,
        result_cache,
    )
    router.include_router(create_benchmark_router(workflow_store, workflow_executor))

    @router.delete("/cache")
    def clear_runtime_cache():
        return workflow_executor.clear_runtime_cache()

    @router.get("/workflows")
    def list_workflows():
        # ``default.json`` is the canonical starter workflow.  Its legacy
        # document payload may say id="workflow", so normalize the public id
        # to the filename-backed route id and never expose it twice.
        default = workflow_store.load(WorkflowStore.DEFAULT_TEMPLATE_ID).model_copy(
            update={"id": WorkflowStore.DEFAULT_TEMPLATE_ID}
        )
        workflows = [default]
        workflows.extend(
            item for item in workflow_store.list()
            if item.id not in (WorkflowStore.DEFAULT_TEMPLATE_ID, WorkflowStore.ACTIVE_WORKFLOW_ID)
        )
        return {"workflows": workflows}

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
            return workflow_executor.cancel_run(run_id)
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404, detail=f"실행 {run_id}를 찾을 수 없습니다"
            ) from error

    return router
