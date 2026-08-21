from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException

from ..core.settings import CACHE_DIR, RUN_DIR, WORKFLOW_DIR
from ..data_sources import INGESTION_WORKFLOW_IDS
from ..runtime.registry import ModuleRegistry
from ..workflows import (
    DagExecutionCancelled,
    DagExecutionError,
    InteractiveWorkflowDispatcher,
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
    workflow_dir: Optional[Path] = None,
    run_dir: Optional[Path] = None,
    cache_dir: Optional[Path] = None,
    workflow_store: Optional[WorkflowStore] = None,
    run_store: Optional[RunStore] = None,
    workflow_executor: Optional[WorkflowExecutor] = None,
    workflow_dispatcher: Optional[InteractiveWorkflowDispatcher] = None,
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
    db_mgr = getattr(module_registry, "db_manager", None)
    run_store = run_store or RunStore(run_dir or RUN_DIR, db_manager=db_mgr)
    workflow_executor = workflow_executor or WorkflowExecutor(
        module_registry,
        run_store,
        ResultCache(cache_dir or CACHE_DIR),
    )
    workflow_dispatcher = workflow_dispatcher or InteractiveWorkflowDispatcher(
        workflow_executor,
        run_store,
    )
    router.include_router(create_benchmark_router(workflow_store, workflow_executor))

    def require_interactive_workflow(workflow_id: str) -> None:
        if workflow_id in INGESTION_WORKFLOW_IDS:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Excel 적재 워크플로는 Data Sources의 Kubernetes 작업 API로만 "
                    "실행할 수 있습니다"
                ),
            )

    def require_interactive_run(run_id: str) -> None:
        require_interactive_workflow(run_store.load(run_id).workflow_id)

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
            require_interactive_workflow(workflow_id)
            workflow = workflow_store.load(workflow_id)
            return workflow_executor.create_run(workflow, request)
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404, detail=f"워크플로 {workflow_id}를 찾을 수 없습니다"
            ) from error
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
            require_interactive_run(run_id)
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
            require_interactive_run(run_id)
            return workflow_executor.execute_node(run_id, node_id)
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
            require_interactive_run(run_id)
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
            require_interactive_run(run_id)
            return workflow_dispatcher.cancel(run_id)
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404, detail=f"실행 {run_id}를 찾을 수 없습니다"
            ) from error

    return router
