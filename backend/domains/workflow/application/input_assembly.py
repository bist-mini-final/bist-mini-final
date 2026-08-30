"""Resolve conditional edges and assemble validated node input payloads."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Tuple

from backend.domains.workflow.domain import DagExecutionError
from backend.engine.runtime.registry_base import BaseModuleRegistry

from .graph_validation import WorkflowPortResolver

if TYPE_CHECKING:
    from backend.engine.workflows.models import WorkflowEdge, WorkflowNode, WorkflowRun


class WorkflowInputAssembler:
    def __init__(
        self,
        module_registry: BaseModuleRegistry,
        port_resolver: WorkflowPortResolver,
    ) -> None:
        self._module_registry = module_registry
        self._port_resolver = port_resolver

    @staticmethod
    def edge_is_active(run: WorkflowRun, edge: WorkflowEdge) -> bool:
        source_state = run.nodes[edge.source]
        if edge.source_branch is None:
            return source_state.status == "succeeded"
        return source_state.outcome == edge.source_branch

    def should_execute(
        self,
        run: WorkflowRun,
        node: WorkflowNode,
    ) -> Tuple[bool, Optional[str]]:
        incoming_edges = [edge for edge in run.graph.edges if edge.target == node.id]
        if not incoming_edges:
            module = self._module_registry.get(node.module_type)
            supplied_fields = set(node.values) | set(
                run.runtime_inputs.get(node.id, {})
            )
            required_inputs = (
                list(module.definition.inputs)
                if module.definition.raw_input
                else module.required_input_fields
            )
            missing_inputs = [
                field for field in required_inputs if field not in supplied_fields
            ]
            if missing_inputs:
                return (
                    False,
                    "연결되지 않은 필수 입력이 있어 건너뜁니다: "
                    + ", ".join(missing_inputs),
                )
            return True, None

        node_by_id = {item.id: item for item in run.graph.nodes}
        edges_by_input: Dict[str, List[WorkflowEdge]] = defaultdict(list)
        for edge in incoming_edges:
            _, target_input = self._port_resolver.resolve(edge, node_by_id)
            edges_by_input[target_input].append(edge)

        module = self._module_registry.get(node.module_type)
        supplied_inputs = (
            set(node.values)
            | set(run.runtime_inputs.get(node.id, {}))
            | set(edges_by_input)
        )
        if not module.definition.raw_input:
            for target_input, alternatives in edges_by_input.items():
                if target_input != "input":
                    continue
                for edge in alternatives:
                    source_node = node_by_id[edge.source]
                    source_module = self._module_registry.get(
                        source_node.module_type
                    )
                    if source_module.definition.raw_output:
                        supplied_inputs.update(source_module.output_model.model_fields)
        missing_inputs = [
            field
            for field in module.required_input_fields
            if field not in supplied_inputs
        ]
        if missing_inputs:
            return (
                False,
                "연결되지 않은 필수 입력이 있어 건너뜁니다: "
                + ", ".join(missing_inputs),
            )

        for target_input, alternatives in edges_by_input.items():
            if not any(self.edge_is_active(run, edge) for edge in alternatives):
                return (
                    False,
                    f"입력 {target_input}에 활성화된 분기 출력이 없어 건너뜁니다",
                )
        return True, None

    def assemble(self, run: WorkflowRun, node: WorkflowNode) -> Any:
        payload = dict(node.values)
        target_module = self._module_registry.get(node.module_type)
        payload.update(run.runtime_inputs.get(node.id, {}))
        node_by_id = {item.id: item for item in run.graph.nodes}
        incoming_edges = [edge for edge in run.graph.edges if edge.target == node.id]
        edges_by_input: Dict[str, List[Tuple[WorkflowEdge, str]]] = defaultdict(list)
        for edge in incoming_edges:
            source_output, target_input = self._port_resolver.resolve(
                edge,
                node_by_id,
            )
            edges_by_input[target_input].append((edge, source_output))

        for target_input, alternatives in edges_by_input.items():
            active_edges = [
                (edge, source_output)
                for edge, source_output in alternatives
                if self.edge_is_active(run, edge)
            ]
            if len(active_edges) != 1:
                raise DagExecutionError(
                    f"노드 {node.id}의 입력 {target_input}에 "
                    f"활성 분기가 {len(active_edges)}개입니다"
                )
            edge, source_output = active_edges[0]
            source_state = run.nodes[edge.source]
            if source_state.status != "succeeded":
                raise DagExecutionError(
                    f"선행 노드 {edge.source}의 출력이 아직 준비되지 않았습니다"
                )
            source_module = self._module_registry.get(
                node_by_id[edge.source].module_type
            ).definition
            if source_module.raw_output:
                source_value = source_state.output
            else:
                if (
                    not isinstance(source_state.output, Mapping)
                    or source_output not in source_state.output
                ):
                    raise DagExecutionError(
                        f"선행 노드 {edge.source}에 출력 {source_output}이 없습니다"
                    )
                source_value = source_state.output[source_output]
            if (
                source_module.raw_output
                and not target_module.definition.raw_input
                and target_input == "input"
            ):
                if not isinstance(source_value, Mapping):
                    raise DagExecutionError(
                        f"선행 노드 {edge.source}의 원본 출력이 객체가 아닙니다"
                    )
                duplicate_fields = set(payload).intersection(source_value)
                if duplicate_fields:
                    raise DagExecutionError(
                        f"노드 {node.id}의 입력과 설정 필드가 충돌합니다: "
                        + ", ".join(sorted(duplicate_fields))
                    )
                payload.update(source_value)
            else:
                payload[target_input] = source_value

        if not target_module.definition.raw_input:
            return payload
        if len(target_module.definition.inputs) != 1:
            raise DagExecutionError(
                f"원본 입력 모듈 {node.module_type}은 입력 포트가 정확히 하나여야 합니다"
            )
        input_port = target_module.definition.inputs[0]
        unknown_fields = set(payload) - {input_port}
        if unknown_fields:
            raise DagExecutionError(
                f"원본 입력 모듈 {node.module_type}에 알 수 없는 값이 있습니다: "
                + ", ".join(sorted(unknown_fields))
            )
        if input_port not in payload:
            raise DagExecutionError(
                f"원본 입력 모듈 {node.module_type}에 {input_port} 값이 없습니다"
            )
        return payload[input_port]


__all__ = ["WorkflowInputAssembler"]
