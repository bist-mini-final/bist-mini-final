"""Execution-policy and Kubernetes queue orchestration tests."""

import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

from pydantic import BaseModel

from modules.common.base_module import (
    EmptyModuleConfigDTO,
    ExecutableModule,
    ModuleDefinition,
    ModuleInputDTO,
    ModuleTaskPolicy,
)
from backend.engine.orchestration import compile_task_plan
from backend.engine.orchestration.kubernetes import KubernetesQueueDispatcher
from backend.engine.runtime.registry_base import BaseModuleRegistry
from backend.storage.db_manager import WorkflowRunAlreadyClaimed, WorkflowRunLease
from backend.engine.workflows.executor import WorkflowExecutor
from backend.engine.workflows.models import (
    CanvasPosition,
    RunBatchState,
    RunNodeState,
    RunOrchestrationState,
    WorkflowEdge,
    WorkflowGraph,
    WorkflowNode,
    WorkflowRun,
)
from backend.engine.workflows.store import ResultCache, RunStore
from jobs.workflow_worker.main import execute_with_policy, run_one


class _ValueInputDTO(ModuleInputDTO):
    value: int


class _ValueOutputDTO(BaseModel):
    value: int


class _SourceModule(ExecutableModule):
    definition = ModuleDefinition(
        type="source",
        label="Source",
        category="Source",
        description="Test source",
        inputs=[],
        outputs=["value"],
        task=ModuleTaskPolicy(tags=["source-test"]),
    )
    input_model = _ValueInputDTO
    config_model = EmptyModuleConfigDTO
    execution_model = _ValueInputDTO
    output_model = _ValueOutputDTO

    def execute(self, payload: BaseModel):
        assert isinstance(payload, _ValueInputDTO)
        self.report_progress(
            {
                "phase": "test_items",
                "completed_items": 1,
                "total_items": 1,
            }
        )
        return {"value": payload.value}


class _DoubleModule(ExecutableModule):
    definition = ModuleDefinition(
        type="double",
        label="Double",
        category="Transform",
        description="Test transform",
        inputs=["value"],
        outputs=["value"],
        task=ModuleTaskPolicy(retries=2, timeout_seconds=30),
    )
    input_model = _ValueInputDTO
    config_model = EmptyModuleConfigDTO
    execution_model = _ValueInputDTO
    output_model = _ValueOutputDTO

    def execute(self, payload: BaseModel):
        assert isinstance(payload, _ValueInputDTO)
        return {"value": payload.value * 2}


class _Registry(BaseModuleRegistry):
    def __init__(self) -> None:
        self.modules = {"source": _SourceModule(), "double": _DoubleModule()}
        self.isolated_worker_spec = None

    def get(self, module_type: str):
        return self.modules[module_type]

    def execute(self, module_type: str, input_payload, config=None):
        return self.get(module_type).run(input_payload, config)

    def clear_caches(self):
        return {}


def _workflow_run() -> WorkflowRun:
    graph = WorkflowGraph(
        nodes=[
            WorkflowNode(
                id="source",
                module_type="source",
                position=CanvasPosition(x=0, y=0),
                values={"value": 3},
            ),
            WorkflowNode(
                id="double",
                module_type="double",
                position=CanvasPosition(x=200, y=0),
            ),
        ],
        edges=[
            WorkflowEdge(
                id="source-double",
                source="source",
                target="double",
                source_output="value",
                target_input="value",
            )
        ],
    )
    return WorkflowRun(
        id="run-kubernetes-test",
        workflow_id="kubernetes-test",
        workflow_updated_at="2026-08-20T00:00:00+00:00",
        graph=graph,
        batches=[
            RunBatchState(index=0, node_ids=["source"]),
            RunBatchState(index=1, node_ids=["double"]),
        ],
        nodes={
            "source": RunNodeState(
                node_id="source", module_type="source", batch_index=0
            ),
            "double": RunNodeState(
                node_id="double", module_type="double", batch_index=1
            ),
        },
    )


def test_module_contract_exposes_kubernetes_task_policy() -> None:
    contract = _DoubleModule().contract()

    assert contract["task"] == {
        "engine": "kubernetes",
        "enabled": True,
        "retries": 2,
        "retry_delay_seconds": 0.0,
        "timeout_seconds": 30.0,
        "tags": [],
        "resource_profile": "standard",
    }


def test_compile_task_plan_preserves_module_identity_and_dependencies() -> None:
    plan = compile_task_plan(_workflow_run(), _Registry())

    assert [(item.node_id, item.module_type) for item in plan] == [
        ("source", "source"),
        ("double", "double"),
    ]
    assert plan[0].upstream_node_ids == ()
    assert plan[1].upstream_node_ids == ("source",)
    assert plan[1].policy.retries == 2


def test_scheduled_nodes_execute_without_invalidating_completed_ancestors() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        store = RunStore(root / "runs")
        store.save(_workflow_run())
        executor = WorkflowExecutor(
            _Registry(),
            store,
            ResultCache(root / "cache"),
        )

        first = executor.execute_scheduled_node("run-kubernetes-test", "source")
        completed = executor.execute_scheduled_node("run-kubernetes-test", "double")

    assert first.nodes["source"].status == "succeeded"
    assert first.nodes["source"].progress == {
        "phase": "test_items",
        "completed_items": 1,
        "total_items": 1,
    }
    assert completed.nodes["source"].status == "succeeded"
    assert completed.nodes["double"].output == {"value": 6}
    assert completed.status == "completed"


def test_kubernetes_dispatcher_persists_durable_queue_submission() -> None:
    with TemporaryDirectory() as directory:
        store = RunStore(Path(directory) / "runs")
        store.save(_workflow_run())
        database = MagicMock()
        store.db_manager = database
        executor = MagicMock()
        dispatcher = KubernetesQueueDispatcher(
            executor,
            store,
            "excel-ingestion",
        )

        assert dispatcher.submit("run-kubernetes-test") is True
        assert dispatcher.submit("run-kubernetes-test") is False
        persisted = store.load_summary("run-kubernetes-test")

    database.enqueue_workflow_run.assert_called_once_with(
        "run-kubernetes-test",
        "excel-ingestion",
        submission_attempt=1,
        submitted_at=persisted.orchestration.submitted_at,
        priority=0,
    )
    assert persisted.orchestration.backend == "kubernetes"
    assert persisted.orchestration.deployment_name == "excel-ingestion"
    assert persisted.orchestration.external_run_id is None
    assert persisted.orchestration.submission_attempt == 1


def test_kubernetes_recovery_skips_runs_already_in_queue() -> None:
    database = MagicMock()
    database.list_pending_workflow_run_references.return_value = [
        {
            "run_id": "run-already-submitted",
            "workflow_id": "indexing_pgvector",
            "status": "queued",
            "orchestration": {
                "backend": "kubernetes",
                "deployment_name": "excel-ingestion",
                "external_run_id": None,
            },
        }
    ]
    store = MagicMock()
    store.db_manager = database
    dispatcher = KubernetesQueueDispatcher(
        MagicMock(),
        store,
        "excel-ingestion",
    )

    recovered = dispatcher.recover_pending({"indexing_pgvector"})

    assert recovered == 0
    database.list_pending_workflow_run_references.assert_called_once_with(
        ["indexing_pgvector"]
    )
    store.load_summary.assert_not_called()


def test_worker_applies_module_retry_policy() -> None:
    services = MagicMock()
    services.workflow_executor.execute_scheduled_node.side_effect = [
        RuntimeError("transient"),
        MagicMock(),
    ]

    execute_with_policy(
        services,
        "run-kubernetes-test",
        "double",
        retries=1,
        retry_delay_seconds=0,
        timeout_seconds=None,
    )

    assert services.workflow_executor.execute_scheduled_node.call_count == 2


def test_worker_skips_advisory_locked_candidate_and_claims_next(
    monkeypatch,
) -> None:
    services = MagicMock()
    locked = WorkflowRunLease("run-locked", "token-locked")
    available = WorkflowRunLease("run-available", "token-available")
    services.db_manager.claim_next_workflow_run.side_effect = [locked, available]
    monkeypatch.setattr(
        "jobs.workflow_worker.main.runtime_services",
        lambda: services,
    )

    def execute_claim(_services, claim, *_args):
        if claim is locked:
            raise WorkflowRunAlreadyClaimed("locked")
        return claim.run_id

    monkeypatch.setattr(
        "jobs.workflow_worker.main._execute_claim",
        execute_claim,
    )

    assert run_one("excel-ingestion", "job-1") == "run-available"
    first_call, second_call = (
        services.db_manager.claim_next_workflow_run.call_args_list
    )
    assert first_call.kwargs["excluded_run_ids"] == ()
    assert second_call.kwargs["excluded_run_ids"] == ("run-locked",)


def test_cancellation_lookup_failure_is_logged_without_masking_execution(
    caplog,
) -> None:
    store = MagicMock()
    store.is_cancel_requested.side_effect = RuntimeError("database unavailable")
    executor = WorkflowExecutor(
        _Registry(),
        store,
        MagicMock(),
    )

    with caplog.at_level(logging.WARNING, logger="backend.engine.workflows.executor"):
        executor._raise_if_cancelled("run-kubernetes-test")

    assert "DB cancellation 상태 조회 실패" in caplog.text
