"""Prefect deployment entrypoint for persisted Excel ingestion workflows."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict

from prefect import flow, task
from prefect.task_runners import ThreadPoolTaskRunner

from backend.core.settings import CACHE_DIR
from backend.data_sources import INGESTION_WORKFLOW_IDS
from backend.data_sources.ingestion_registry import IngestionModuleRegistry
from backend.orchestration import compile_task_plan
from backend.runtime.services import (
    WorkflowRuntimeServices,
    create_workflow_runtime_services,
)
from backend.storage.answer_cache import AnswerCacheRepository


@lru_cache(maxsize=1)
def _runtime_services() -> WorkflowRuntimeServices:
    """Build the lean ingestion runtime once per one-shot flow container."""

    return create_workflow_runtime_services(
        AnswerCacheRepository(CACHE_DIR / "answers.json"),
        initialize_schema=False,
        require_database=True,
        registry_factory=IngestionModuleRegistry,
    )


@task(
    name="playground-module",
    task_run_name="{module_type}:{node_id}",
    persist_result=False,
)
def execute_persisted_module_task(
    run_id: str,
    node_id: str,
    module_type: str,
) -> Dict[str, Any]:
    """Execute one product module while preserving the existing run DTO."""

    services = _runtime_services()
    run = services.run_store.load(run_id)
    state = run.nodes.get(node_id)
    if state is None or state.module_type != module_type:
        raise ValueError(
            f"run의 노드 계약과 Prefect task가 다릅니다: {node_id}/{module_type}"
        )
    run = services.workflow_executor.execute_scheduled_node(run_id, node_id)
    state = run.nodes[node_id]
    return {
        "run_id": run_id,
        "node_id": node_id,
        "module_type": module_type,
        "status": state.status,
        "outcome": state.outcome,
        "cache_hit": state.cache_hit,
    }


@flow(  # pyright: ignore[reportCallIssue]
    name="excel-ingestion",
    flow_run_name="excel-ingestion-{run_id}",
    task_runner=ThreadPoolTaskRunner(max_workers=1),  # pyright: ignore[reportArgumentType]
    persist_result=False,
    log_prints=True,
)
def excel_ingestion_flow(
    run_id: str,
    resume_failed: bool = False,
) -> Dict[str, Any]:
    """Compile every Playground module into a Prefect task and execute the DAG.

    Task concurrency is intentionally one within a flow until node state writes
    become atomic. Docker still runs independent ingestion requests in separate
    flow-run containers, providing the requested request-level parallelism.
    """

    services = _runtime_services()
    with services.db_manager.claim_workflow_run(run_id):
        run = services.run_store.load(run_id)
        if run.workflow_id not in INGESTION_WORKFLOW_IDS:
            raise ValueError(
                f"Excel 적재 flow가 처리할 수 없는 workflow입니다: {run.workflow_id}"
            )
        if resume_failed or run.status in ("failed", "paused"):
            run = services.workflow_executor.prepare_resume(run_id)

        plan = compile_task_plan(run, services.module_registry)
        futures: Dict[str, Any] = {}
        for planned in plan:
            policy = planned.policy
            module_task = execute_persisted_module_task.with_options(
                name=f"{planned.label} [{planned.module_type}]",
                retries=policy.retries,
                retry_delay_seconds=policy.retry_delay_seconds,
                timeout_seconds=policy.timeout_seconds,
                tags=[
                    "playground-module",
                    f"module:{planned.module_type}",
                    f"resource:{policy.resource_profile}",
                    *policy.tags,
                ],
            )
            futures[planned.node_id] = module_task.submit(  # pyright: ignore[reportCallIssue]
                run_id=run_id,
                node_id=planned.node_id,
                module_type=planned.module_type,
                wait_for=[futures[node_id] for node_id in planned.upstream_node_ids],
            )

        for planned in plan:
            futures[planned.node_id].result()

        completed = services.run_store.load(run_id)
        if completed.status != "completed":
            raise RuntimeError(
                f"Excel 적재 run이 완료되지 않았습니다: {completed.status}"
            )
        return {
            "run_id": completed.id,
            "workflow_id": completed.workflow_id,
            "status": completed.status,
            "module_count": len(plan),
        }
