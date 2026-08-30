"""Graph and pin-contract validation independent of execution scheduling."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Dict, List, Mapping, Set, Tuple

import networkx as nx
from pydantic import ValidationError

from backend.domains.workflow.domain import (
    DagExecutionError,
    format_execution_error,
)
from backend.engine.runtime.registry_base import BaseModuleRegistry

if TYPE_CHECKING:
    from backend.engine.workflows.models import (
        WorkflowEdge,
        WorkflowGraph,
        WorkflowNode,
    )


class WorkflowPortResolver:
    def __init__(self, module_registry: BaseModuleRegistry) -> None:
        self._module_registry = module_registry

    def resolve(
        self,
        edge: WorkflowEdge,
        node_by_id: Mapping[str, WorkflowNode],
    ) -> Tuple[str, str]:
        source_module = self._module_registry.get(node_by_id[edge.source].module_type).definition
        target_module = self._module_registry.get(node_by_id[edge.target].module_type).definition

        source_output = edge.source_output
        if edge.source_branch is not None:
            branch_output = source_module.branch_outputs.get(edge.source_branch)
            if branch_output is None:
                raise DagExecutionError(
                    f"모듈 {source_module.type}에 {edge.source_branch} 분기 출력이 없습니다"
                )
            if source_output is not None and source_output != branch_output:
                raise DagExecutionError(
                    f"{edge.source_branch} 분기는 {branch_output} 출력만 사용할 수 있습니다"
                )
            source_output = branch_output
        if source_output is None:
            if len(source_module.outputs) != 1:
                raise DagExecutionError(f"연결 {edge.id}의 source_output을 지정해야 합니다")
            source_output = source_module.outputs[0]
        if source_output not in source_module.outputs:
            raise DagExecutionError(
                f"모듈 {source_module.type}에 출력 포트 {source_output}이 없습니다"
            )

        target_input = edge.target_input
        if target_input is None:
            if len(target_module.inputs) != 1:
                raise DagExecutionError(f"연결 {edge.id}의 target_input을 지정해야 합니다")
            target_input = target_module.inputs[0]
        if target_input not in target_module.inputs:
            raise DagExecutionError(
                f"모듈 {target_module.type}에 입력 포트 {target_input}이 없습니다"
            )
        return source_output, target_input


class WorkflowGraphValidator:
    def __init__(
        self,
        module_registry: BaseModuleRegistry,
        port_resolver: WorkflowPortResolver,
    ) -> None:
        self._module_registry = module_registry
        self._port_resolver = port_resolver

    def validate(self, graph: WorkflowGraph) -> List[List[str]]:
        if not graph.nodes:
            raise DagExecutionError("실행할 노드가 없습니다")

        node_by_id = self._validated_nodes(graph.nodes)
        graph_dag = self._validated_edges(graph.edges, node_by_id)
        return self._topological_batches(graph_dag)

    def _validated_nodes(
        self,
        nodes: List[WorkflowNode],
    ) -> Dict[str, WorkflowNode]:
        node_by_id: Dict[str, WorkflowNode] = {}
        for node in nodes:
            if node.id in node_by_id:
                raise DagExecutionError(f"중복 노드 ID입니다: {node.id}")
            self._validate_node_contract(node)
            node_by_id[node.id] = node
        return node_by_id

    def _validate_node_contract(self, node: WorkflowNode) -> None:
        try:
            module = self._module_registry.get(node.module_type)
        except KeyError as error:
            raise DagExecutionError(str(error)) from error

        unknown_config = set(node.config) - set(module.config_fields)
        if unknown_config:
            raise DagExecutionError(
                f"노드 {node.id}의 config에 설정 필드가 아닌 값이 있습니다: "
                + ", ".join(sorted(unknown_config))
            )
        try:
            module.validate_config(node.config)
        except ValidationError as error:
            raise DagExecutionError(
                f"노드 {node.id}의 config가 유효하지 않습니다: " + format_execution_error(error)
            ) from error

        allowed_value_fields = (
            set(module.definition.inputs)
            if module.definition.raw_input
            else set(module.input_fields)
        )
        unknown_values = set(node.values) - allowed_value_fields
        if unknown_values:
            raise DagExecutionError(
                f"노드 {node.id}의 values에 Input DTO 필드가 아닌 값이 있습니다: "
                + ", ".join(sorted(unknown_values))
            )

    def _validated_edges(
        self,
        edges: List[WorkflowEdge],
        node_by_id: Mapping[str, WorkflowNode],
    ) -> nx.DiGraph:
        edge_ids: Set[str] = set()
        occupied_inputs: Dict[Tuple[str, str], List[WorkflowEdge]] = defaultdict(list)
        graph_dag = nx.DiGraph()
        graph_dag.add_nodes_from(node_by_id)

        for edge in edges:
            self._validate_edge_identity(edge, edge_ids, node_by_id)
            _, target_input = self._port_resolver.resolve(edge, node_by_id)
            self._claim_target_input(edge, target_input, occupied_inputs)
            graph_dag.add_edge(edge.source, edge.target)
        return graph_dag

    @staticmethod
    def _validate_edge_identity(
        edge: WorkflowEdge,
        edge_ids: Set[str],
        node_by_id: Mapping[str, WorkflowNode],
    ) -> None:
        if edge.id in edge_ids:
            raise DagExecutionError(f"중복 연결 ID입니다: {edge.id}")
        edge_ids.add(edge.id)
        if edge.source not in node_by_id or edge.target not in node_by_id:
            raise DagExecutionError(f"연결 {edge.id}이 존재하지 않는 노드를 참조합니다")
        if edge.source == edge.target:
            raise DagExecutionError(f"자기 자신으로 연결할 수 없습니다: {edge.id}")

    @staticmethod
    def _claim_target_input(
        edge: WorkflowEdge,
        target_input: str,
        occupied_inputs: Dict[Tuple[str, str], List[WorkflowEdge]],
    ) -> None:
        alternatives = occupied_inputs[(edge.target, target_input)]
        existing_branches = {candidate.source_branch for candidate in alternatives}
        is_valid_branch_group = not alternatives or (
            edge.source_branch is not None
            and None not in existing_branches
            and edge.source_branch not in existing_branches
            and all(candidate.source == edge.source for candidate in alternatives)
        )
        if not is_valid_branch_group:
            raise DagExecutionError(
                f"노드 {edge.target}의 입력 {target_input}에 호환되지 않는 여러 연결이 들어옵니다"
            )
        alternatives.append(edge)

    @staticmethod
    def _topological_batches(graph_dag: nx.DiGraph) -> List[List[str]]:
        if nx.is_directed_acyclic_graph(graph_dag):
            return [list(generation) for generation in nx.topological_generations(graph_dag)]
        try:
            cycle = nx.find_cycle(graph_dag, orientation="original")
        except Exception as error:
            raise DagExecutionError("순환 연결이 감지되었습니다") from error
        cycle_str = " -> ".join([source for source, _, _ in cycle] + [cycle[0][0]])
        raise DagExecutionError(f"순환 연결이 감지되었습니다: {cycle_str}")


__all__ = ["WorkflowGraphValidator", "WorkflowPortResolver"]
