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
        node_by_id = {item.id: item for item in run.graph.nodes}
        edges_by_input = self._edges_by_input(run, node, node_by_id)
        module = self._module_registry.get(node.module_type)
        supplied_inputs = self._supplied_inputs(
            run,
            node,
            node_by_id,
            edges_by_input,
        )
        required_inputs = (
            list(module.definition.inputs)
            if module.definition.raw_input
            else module.required_input_fields
        )
        missing_inputs = [field for field in required_inputs if field not in supplied_inputs]
        if missing_inputs:
            return False, self._missing_input_reason(missing_inputs)

        for target_input, alternatives in edges_by_input.items():
            if not any(self.edge_is_active(run, edge) for edge, _source_output in alternatives):
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
        edges_by_input = self._edges_by_input(run, node, node_by_id)
        for target_input, alternatives in edges_by_input.items():
            edge, source_output = self._active_edge(node, target_input, alternatives, run)
            source_module, source_value = self._source_value(
                run,
                node_by_id,
                edge,
                source_output,
            )
            self._bind_value(
                payload,
                node,
                target_input,
                target_module.definition.raw_input,
                source_module.raw_output,
                source_value,
                edge,
            )
        return self._unwrap_raw_input(payload, node, target_module.definition)

    def _edges_by_input(
        self,
        run: WorkflowRun,
        node: WorkflowNode,
        node_by_id: Mapping[str, WorkflowNode],
    ) -> Dict[str, List[Tuple[WorkflowEdge, str]]]:
        edges_by_input: Dict[str, List[Tuple[WorkflowEdge, str]]] = defaultdict(list)
        for edge in run.graph.edges:
            if edge.target != node.id:
                continue
            source_output, target_input = self._port_resolver.resolve(edge, node_by_id)
            edges_by_input[target_input].append((edge, source_output))
        return edges_by_input

    def _supplied_inputs(
        self,
        run: WorkflowRun,
        node: WorkflowNode,
        node_by_id: Mapping[str, WorkflowNode],
        edges_by_input: Mapping[str, List[Tuple[WorkflowEdge, str]]],
    ) -> set[str]:
        supplied = set(node.values) | set(run.runtime_inputs.get(node.id, {})) | set(edges_by_input)
        module = self._module_registry.get(node.module_type)
        if module.definition.raw_input or "input" not in edges_by_input:
            return supplied
        for edge, _source_output in edges_by_input["input"]:
            source_node = node_by_id[edge.source]
            source_module = self._module_registry.get(source_node.module_type)
            if source_module.definition.raw_output:
                supplied.update(source_module.output_model.model_fields)
        return supplied

    @staticmethod
    def _missing_input_reason(missing_inputs: List[str]) -> str:
        return "연결되지 않은 필수 입력이 있어 건너뜁니다: " + ", ".join(missing_inputs)

    @classmethod
    def _active_edge(
        cls,
        node: WorkflowNode,
        target_input: str,
        alternatives: List[Tuple[WorkflowEdge, str]],
        run: WorkflowRun,
    ) -> Tuple[WorkflowEdge, str]:
        active_edges = [binding for binding in alternatives if cls.edge_is_active(run, binding[0])]
        if len(active_edges) != 1:
            raise DagExecutionError(
                f"노드 {node.id}의 입력 {target_input}에 활성 분기가 {len(active_edges)}개입니다"
            )
        return active_edges[0]

    def _source_value(
        self,
        run: WorkflowRun,
        node_by_id: Mapping[str, WorkflowNode],
        edge: WorkflowEdge,
        source_output: str,
    ) -> Tuple[Any, Any]:
        source_state = run.nodes[edge.source]
        if source_state.status != "succeeded":
            raise DagExecutionError(f"선행 노드 {edge.source}의 출력이 아직 준비되지 않았습니다")
        source_module = self._module_registry.get(node_by_id[edge.source].module_type).definition
        if source_module.raw_output:
            return source_module, source_state.output
        if not isinstance(source_state.output, Mapping) or source_output not in source_state.output:
            raise DagExecutionError(f"선행 노드 {edge.source}에 출력 {source_output}이 없습니다")
        return source_module, source_state.output[source_output]

    @staticmethod
    def _bind_value(
        payload: Dict[str, Any],
        node: WorkflowNode,
        target_input: str,
        target_raw_input: bool,
        source_raw_output: bool,
        source_value: Any,
        edge: WorkflowEdge,
    ) -> None:
        if not (source_raw_output and not target_raw_input and target_input == "input"):
            payload[target_input] = source_value
            return
        if not isinstance(source_value, Mapping):
            raise DagExecutionError(f"선행 노드 {edge.source}의 원본 출력이 객체가 아닙니다")
        duplicate_fields = set(payload).intersection(source_value)
        if duplicate_fields:
            raise DagExecutionError(
                f"노드 {node.id}의 입력과 설정 필드가 충돌합니다: "
                + ", ".join(sorted(duplicate_fields))
            )
        payload.update(source_value)

    @staticmethod
    def _unwrap_raw_input(payload: Dict[str, Any], node: WorkflowNode, definition: Any) -> Any:
        if not definition.raw_input:
            return payload
        if len(definition.inputs) != 1:
            raise DagExecutionError(
                f"원본 입력 모듈 {node.module_type}은 입력 포트가 정확히 하나여야 합니다"
            )
        input_port = definition.inputs[0]
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
