"""Compile a persisted Playground DAG into portable task invocations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from backend.engine.runtime.registry_base import BaseModuleRegistry
from backend.engine.workflows.models import WorkflowRun
from modules.common.base_module import ModuleTaskPolicy


@dataclass(frozen=True)
class CompiledTaskNode:
    """One module invocation and the upstream tasks a worker must await."""

    node_id: str
    module_type: str
    label: str
    batch_index: int
    upstream_node_ids: Tuple[str, ...]
    policy: ModuleTaskPolicy


def compile_task_plan(
    run: WorkflowRun,
    module_registry: BaseModuleRegistry,
) -> Tuple[CompiledTaskNode, ...]:
    """Project the product-owned graph into a deterministic task plan."""

    dependencies = {node.id: set() for node in run.graph.nodes}
    for edge in run.graph.edges:
        dependencies[edge.target].add(edge.source)

    nodes_by_id = {node.id: node for node in run.graph.nodes}
    compiled = []
    for batch in sorted(run.batches, key=lambda item: item.index):
        for node_id in batch.node_ids:
            node = nodes_by_id[node_id]
            module = module_registry.get(node.module_type)
            policy = module.definition.task or module.definition.task_policy
            if not policy.enabled:
                raise ValueError(
                    f"배치 실행이 비활성화된 모듈입니다: {node.module_type}"
                )
            compiled.append(
                CompiledTaskNode(
                    node_id=node.id,
                    module_type=node.module_type,
                    label=module.definition.label,
                    batch_index=batch.index,
                    upstream_node_ids=tuple(sorted(dependencies[node.id])),
                    policy=policy,
                )
            )
    return tuple(compiled)
