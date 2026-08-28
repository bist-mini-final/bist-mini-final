from __future__ import annotations

from threading import Barrier

from pydantic import BaseModel

from backend.engine.runtime.registry_base import BaseModuleRegistry
from backend.engine.workflows.executor import WorkflowExecutor
from backend.engine.workflows.models import (
    CanvasPosition,
    WorkflowDocument,
    WorkflowExecutionRequest,
    WorkflowGraph,
    WorkflowNode,
)
from backend.engine.workflows.store import ResultCache, RunStore
from backend.storage.embedding_artifacts import EmbeddingArtifactStore
from modules.common.base_module import (
    BaseModule,
    EmptyModuleConfigDTO,
    ModuleDefinition,
    ModuleInputDTO,
    ModuleTaskPolicy,
)


class ParallelInput(ModuleInputDTO):
    value: str


class ParallelOutput(BaseModel):
    result: str


def parallel_module(
    module_type: str,
    barrier: Barrier,
) -> BaseModule:
    class ParallelModule(BaseModule):
        definition = ModuleDefinition(
            type=module_type,
            label=module_type,
            category="test",
            description="TaskGroup concurrency probe",
            inputs=["value"],
            outputs=["result"],
            config_fields=[],
            version="1",
            task_policy=ModuleTaskPolicy(task_affinity="io"),
        )
        input_model = ParallelInput
        config_model = EmptyModuleConfigDTO
        output_model = ParallelOutput

        def execute(self, input_data, config=None):
            barrier.wait(timeout=1)
            return ParallelOutput(result=input_data.value)

    return ParallelModule()


def test_task_group_merges_parallel_node_states_without_lost_updates(tmp_path) -> None:
    barrier = Barrier(2)
    registry = BaseModuleRegistry(EmbeddingArtifactStore(tmp_path / "artifacts"))
    registry.register(
        (
            parallel_module("parallel_a", barrier),
            parallel_module("parallel_b", barrier),
        )
    )
    run_store = RunStore()
    executor = WorkflowExecutor(registry, run_store, ResultCache())
    workflow = WorkflowDocument(
        id="parallel-workflow",
        name="Parallel workflow",
        updated_at="2026-08-28T00:00:00+00:00",
        graph=WorkflowGraph(
            nodes=[
                WorkflowNode(
                    id="a",
                    module_type="parallel_a",
                    position=CanvasPosition(x=0, y=0),
                    values={"value": "A"},
                ),
                WorkflowNode(
                    id="b",
                    module_type="parallel_b",
                    position=CanvasPosition(x=200, y=0),
                    values={"value": "B"},
                ),
            ]
        ),
    )
    run = executor.create_run(workflow, WorkflowExecutionRequest(use_cache=False))

    completed = executor.execute_scheduled_batch(run.id, ("a", "b"))

    assert completed.status == "completed"
    assert completed.nodes["a"].status == "succeeded"
    assert completed.nodes["a"].output == {"result": "A"}
    assert completed.nodes["b"].status == "succeeded"
    assert completed.nodes["b"].output == {"result": "B"}
    assert run_store.load(run.id).nodes["a"].output == {"result": "A"}
    assert run_store.load(run.id).nodes["b"].output == {"result": "B"}


def test_task_group_uses_native_async_module_hook(tmp_path) -> None:
    class NativeAsyncModule(BaseModule):
        definition = ModuleDefinition(
            type="native_async",
            label="native_async",
            category="test",
            description="Native async execution probe",
            inputs=["value"],
            outputs=["result"],
            config_fields=[],
        )
        input_model = ParallelInput
        config_model = EmptyModuleConfigDTO
        output_model = ParallelOutput

        def execute(self, input_data, config=None):
            raise AssertionError("workflow called sync execute")

        async def execute_async(self, input_data, config=None):
            return ParallelOutput(result=f"async:{input_data.value}")

    registry = BaseModuleRegistry(EmbeddingArtifactStore(tmp_path / "artifacts"))
    registry.register((NativeAsyncModule(),))
    run_store = RunStore()
    executor = WorkflowExecutor(registry, run_store, ResultCache())
    workflow = WorkflowDocument(
        id="native-async-workflow",
        name="Native async workflow",
        updated_at="2026-08-28T00:00:00+00:00",
        graph=WorkflowGraph(
            nodes=[
                WorkflowNode(
                    id="native",
                    module_type="native_async",
                    position=CanvasPosition(x=0, y=0),
                    values={"value": "ok"},
                )
            ]
        ),
    )
    run = executor.create_run(workflow, WorkflowExecutionRequest(use_cache=False))

    completed = executor.execute_scheduled_batch(run.id, ("native",))

    assert completed.nodes["native"].output == {"result": "async:ok"}
