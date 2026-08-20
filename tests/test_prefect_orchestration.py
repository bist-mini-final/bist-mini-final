from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pydantic import BaseModel

from backend.modules.base import (
    EmptyModuleConfigDTO,
    ExecutableModule,
    ModuleDefinition,
    ModuleInputDTO,
    ModuleTaskPolicy,
)
from backend.orchestration import compile_task_plan
from backend.orchestration.prefect import (
    PrefectSdkDeploymentClient,
    PrefectIngestionDispatcher,
)
from backend.runtime.registry_base import BaseModuleRegistry
from backend.workflows.executor import WorkflowExecutor
from backend.workflows.models import (
    CanvasPosition,
    RunBatchState,
    RunNodeState,
    WorkflowEdge,
    WorkflowGraph,
    WorkflowNode,
    WorkflowRun,
)
from backend.workflows.store import ResultCache, RunStore


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
        id="run-prefect-test",
        workflow_id="prefect-test",
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


def test_module_contract_exposes_prefect_task_policy() -> None:
    contract = _DoubleModule().contract()

    assert contract["task"] == {
        "engine": "prefect",
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

        first = executor.execute_scheduled_node("run-prefect-test", "source")
        completed = executor.execute_scheduled_node("run-prefect-test", "double")

    assert first.nodes["source"].status == "succeeded"
    assert first.nodes["source"].progress == {
        "phase": "test_items",
        "completed_items": 1,
        "total_items": 1,
    }
    assert completed.nodes["source"].status == "succeeded"
    assert completed.nodes["double"].output == {"value": 6}
    assert completed.status == "completed"


def test_prefect_dispatcher_persists_external_run_identity() -> None:
    with TemporaryDirectory() as directory:
        store = RunStore(Path(directory) / "runs")
        store.save(_workflow_run())
        executor = MagicMock()
        client = MagicMock()
        client.submit.return_value = "00000000-0000-0000-0000-000000000123"
        dispatcher = PrefectIngestionDispatcher(
            executor,
            store,
            "excel-ingestion/docker",
            client,
        )

        assert dispatcher.submit("run-prefect-test") is True
        assert dispatcher.submit("run-prefect-test") is False
        persisted = store.load("run-prefect-test")

    client.submit.assert_called_once_with(
        "excel-ingestion/docker",
        run_id="run-prefect-test",
        resume_failed=False,
        submission_attempt=1,
    )
    assert persisted.orchestration.backend == "prefect"
    assert persisted.orchestration.external_run_id == client.submit.return_value
    assert persisted.orchestration.submission_attempt == 1


def test_prefect_sdk_client_resolves_submission_returned_as_coroutine() -> None:
    expected_id = "00000000-0000-0000-0000-000000000456"

    async def async_run_deployment(**_kwargs):
        return SimpleNamespace(id=expected_id)

    with patch(
        "prefect.deployments.run_deployment",
        side_effect=async_run_deployment,
    ):
        submitted_id = PrefectSdkDeploymentClient().submit(
            "excel-ingestion/docker",
            run_id="run-prefect-async-test",
            resume_failed=False,
            submission_attempt=1,
        )

    assert submitted_id == expected_id


def test_prefect_recovery_skips_runs_already_owned_without_loading_payload() -> None:
    database = MagicMock()
    database.list_pending_workflow_run_references.return_value = [
        {
            "run_id": "run-already-submitted",
            "workflow_id": "indexing_pgvector",
            "status": "queued",
            "orchestration": {
                "backend": "prefect",
                "external_run_id": "00000000-0000-0000-0000-000000000789",
            },
        }
    ]
    store = MagicMock()
    store.db_manager = database
    response = MagicMock()
    response.__enter__.return_value.status = 200
    dispatcher = PrefectIngestionDispatcher(
        MagicMock(),
        store,
        "excel-ingestion/docker",
        MagicMock(),
    )

    with patch("urllib.request.urlopen", return_value=response):
        recovered = dispatcher.recover_pending({"indexing_pgvector"})

    assert recovered == 0
    database.list_pending_workflow_run_references.assert_called_once_with(
        ["indexing_pgvector"]
    )
    store.load.assert_not_called()
