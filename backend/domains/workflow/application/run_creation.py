"""Create validated workflow-run snapshots from immutable workflow definitions."""

from __future__ import annotations

from uuid import uuid4

from backend.domains.workflow.domain import DagExecutionError
from backend.engine.runtime.registry_base import BaseModuleRegistry
from backend.engine.workflows.models import (
    RunBatchState,
    RunNodeState,
    WorkflowDocument,
    WorkflowExecutionRequest,
    WorkflowRun,
)

from .graph_validation import WorkflowGraphValidator
from .ports import WorkflowRunRepository


class WorkflowRunFactory:
    """Validate runtime intent and persist the initial execution snapshot."""

    def __init__(
        self,
        module_registry: BaseModuleRegistry,
        graph_validator: WorkflowGraphValidator,
        run_store: WorkflowRunRepository,
    ) -> None:
        self._module_registry = module_registry
        self._graph_validator = graph_validator
        self._run_store = run_store

    def create(
        self,
        workflow: WorkflowDocument,
        request: WorkflowExecutionRequest,
    ) -> WorkflowRun:
        execution_graph = workflow.graph.model_copy(deep=True)
        known_nodes = {node.id for node in execution_graph.nodes}
        self._validate_node_references(request, known_nodes)

        for node in execution_graph.nodes:
            override = request.config_overrides.get(node.id)
            if override:
                node.config = {**node.config, **override}

        batches = self._graph_validator.validate(execution_graph)
        nodes_by_id = {node.id: node for node in execution_graph.nodes}
        for node_id, runtime_input in request.inputs.items():
            node = nodes_by_id[node_id]
            module = self._module_registry.get(node.module_type)
            allowed_fields = (
                set(module.definition.inputs)
                if module.definition.raw_input
                else set(module.input_fields)
            )
            unknown_fields = set(runtime_input) - allowed_fields
            if unknown_fields:
                raise DagExecutionError(
                    f"노드 {node_id}의 실행 입력에 연결 입력이 아닌 값이 있습니다: "
                    + ", ".join(sorted(unknown_fields))
                    + ". 모듈 설정은 workflow node.config에 저장하세요"
                )

        batch_index_by_node = {
            node_id: batch_index
            for batch_index, node_ids in enumerate(batches)
            for node_id in node_ids
        }
        run = WorkflowRun(
            id=f"run-{uuid4().hex}",
            workflow_id=workflow.id,
            workflow_updated_at=workflow.updated_at,
            graph=execution_graph,
            runtime_inputs=request.inputs,
            use_cache=request.use_cache,
            cache_only_module_types=request.cache_only_module_types,
            batches=[
                RunBatchState(index=index, node_ids=node_ids)
                for index, node_ids in enumerate(batches)
            ],
            nodes={
                node.id: RunNodeState(
                    node_id=node.id,
                    module_type=node.module_type,
                    batch_index=batch_index_by_node[node.id],
                )
                for node in execution_graph.nodes
            },
        )
        return self._run_store.save(run)

    @staticmethod
    def _validate_node_references(
        request: WorkflowExecutionRequest,
        known_nodes: set[str],
    ) -> None:
        unknown_inputs = sorted(set(request.inputs) - known_nodes)
        if unknown_inputs:
            raise DagExecutionError(
                "실행 입력이 존재하지 않는 노드를 참조합니다: " + ", ".join(unknown_inputs)
            )
        unknown_config_nodes = sorted(set(request.config_overrides) - known_nodes)
        if unknown_config_nodes:
            raise DagExecutionError(
                "실행 설정이 존재하지 않는 노드를 참조합니다: "
                + ", ".join(unknown_config_nodes)
            )


__all__ = ["WorkflowRunFactory"]
