from collections import defaultdict
import logging
from threading import Lock, RLock
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple
from uuid import uuid4

from pydantic import ValidationError

from backend.engine.runtime.registry_base import BaseModuleRegistry
from backend.engine.runtime.worker import (
    CancellableModuleWorker,
    ModuleWorkerCancelled,
)
from modules.common.base_module import ModuleExecutionError
from .models import (
    RunBatchState,
    RunNodeState,
    WorkflowDocument,
    WorkflowEdge,
    WorkflowExecutionRequest,
    WorkflowGraph,
    WorkflowNode,
    WorkflowRun,
    utc_now_iso,
)
from .history import compact_history_value
from .store import ResultCache, RunStore


logger = logging.getLogger(__name__)


class DagExecutionError(ValueError):
    """Raised when a workflow graph or its persisted execution is invalid."""


class DagExecutionCancelled(RuntimeError):
    """Raised after a user-requested run cancellation has been persisted."""


class WorkflowExecutor:
    """Runs ready DAG nodes in batches and persists every node transition."""

    def __init__(
        self,
        module_registry: BaseModuleRegistry,
        run_store: RunStore,
        result_cache: ResultCache,
        module_worker: Any = None,
    ) -> None:
        self.module_registry = module_registry
        self.run_store = run_store
        self.result_cache = result_cache
        self._execution_lock = RLock()
        self._cancellation_lock = Lock()
        self._active_run_ids: Set[str] = set()
        self._cancelled_run_ids: Set[str] = set()
        worker_spec = module_registry.isolated_worker_spec
        self._module_worker = (
            module_worker
            if module_worker is not None
            else CancellableModuleWorker(worker_spec)
            if worker_spec is not None
            else None
        )

    def validate_graph(self, graph: WorkflowGraph) -> List[List[str]]:
        if not graph.nodes:
            raise DagExecutionError("실행할 노드가 없습니다")

        node_by_id: Dict[str, WorkflowNode] = {}
        for node in graph.nodes:
            if node.id in node_by_id:
                raise DagExecutionError(f"중복 노드 ID입니다: {node.id}")
            try:
                module = self.module_registry.get(node.module_type)
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
                    f"노드 {node.id}의 config가 유효하지 않습니다: "
                    + self._format_error(error)
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
            node_by_id[node.id] = node

        edge_ids: Set[str] = set()
        occupied_inputs: Dict[Tuple[str, str], List[WorkflowEdge]] = defaultdict(list)
        dependencies: Set[Tuple[str, str]] = set()
        indegree = {node.id: 0 for node in graph.nodes}
        outgoing: Dict[str, List[str]] = defaultdict(list)

        for edge in graph.edges:
            if edge.id in edge_ids:
                raise DagExecutionError(f"중복 연결 ID입니다: {edge.id}")
            edge_ids.add(edge.id)
            if edge.source not in node_by_id or edge.target not in node_by_id:
                raise DagExecutionError(
                    f"연결 {edge.id}이 존재하지 않는 노드를 참조합니다"
                )
            if edge.source == edge.target:
                raise DagExecutionError(f"자기 자신으로 연결할 수 없습니다: {edge.id}")

            _, target_input = self._resolve_ports(edge, node_by_id)
            occupied = (edge.target, target_input)
            alternatives = occupied_inputs[occupied]
            if alternatives:
                existing_branches = {candidate.source_branch for candidate in alternatives}
                is_valid_branch_group = (
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

            dependency = (edge.source, edge.target)
            if dependency not in dependencies:
                dependencies.add(dependency)
                indegree[edge.target] += 1
                outgoing[edge.source].append(edge.target)

        remaining = dict(indegree)
        current = [node.id for node in graph.nodes if remaining[node.id] == 0]
        batches: List[List[str]] = []
        visited = 0
        while current:
            batches.append(current)
            visited += len(current)
            next_nodes: List[str] = []
            for node_id in current:
                for target_id in outgoing[node_id]:
                    remaining[target_id] -= 1
                    if remaining[target_id] == 0:
                        next_nodes.append(target_id)
            current = next_nodes

        if visited != len(graph.nodes):
            cycle_nodes = [node_id for node_id, count in remaining.items() if count > 0]
            raise DagExecutionError(
                "순환 연결이 감지되었습니다: " + ", ".join(cycle_nodes)
            )
        return batches

    def create_run(
        self,
        workflow: WorkflowDocument,
        request: WorkflowExecutionRequest,
    ) -> WorkflowRun:
        """
        Create and persist a workflow run from the requested inputs and configuration.
        
        Parameters:
            workflow (WorkflowDocument): Workflow definition to execute.
            request (WorkflowExecutionRequest): Runtime inputs, configuration overrides, cache settings, and optional run inheritance settings.
        
        Returns:
            WorkflowRun: The newly created and persisted workflow run.
        
        Raises:
            DagExecutionError: If the request references unknown nodes or contains invalid runtime inputs, or if the workflow graph is invalid.
        """
        execution_graph = workflow.graph.model_copy(deep=True)
        known_nodes = {node.id for node in execution_graph.nodes}
        unknown_inputs = sorted(set(request.inputs) - known_nodes)
        if unknown_inputs:
            raise DagExecutionError(
                "실행 입력이 존재하지 않는 노드를 참조합니다: "
                + ", ".join(unknown_inputs)
            )
        unknown_config_nodes = sorted(set(request.config_overrides) - known_nodes)
        if unknown_config_nodes:
            raise DagExecutionError(
                "실행 설정이 존재하지 않는 노드를 참조합니다: "
                + ", ".join(unknown_config_nodes)
            )

        for node in execution_graph.nodes:
            override = request.config_overrides.get(node.id)
            if override:
                node.config = {**node.config, **override}

        batches = self.validate_graph(execution_graph)
        for node_id, runtime_input in request.inputs.items():
            node = next(
                item for item in execution_graph.nodes if item.id == node_id
            )
            module = self.module_registry.get(node.module_type)
            if module.definition.raw_input:
                allowed_fields = set(module.definition.inputs)
            else:
                allowed_fields = set(module.input_fields)
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

        # Collect node states to inherit from a previous run when only new nodes
        # have been added.  Only nodes that (a) still exist in the new graph with
        # the same module_type and config, and (b) completed successfully are
        # copied so that upstream branch checks pass for the new node.
        inherited_states: Dict[str, RunNodeState] = {}
        if request.inherit_from_run_id:
            try:
                prev_run = self.run_store.load(request.inherit_from_run_id)
                # Build a lookup of the new graph's nodes
                new_node_map = {
                    node.id: node for node in execution_graph.nodes
                }
                new_edge_set = {
                    (e.source, e.target, e.source_output, e.target_input, e.source_branch)
                    for e in execution_graph.edges
                }
                prev_edge_set = {
                    (e.source, e.target, e.source_output, e.target_input, e.source_branch)
                    for e in prev_run.graph.edges
                }
                for prev_node in prev_run.graph.nodes:
                    new_node = new_node_map.get(prev_node.id)
                    if new_node is None:
                        continue  # node was removed — skip
                    if new_node.module_type != prev_node.module_type:
                        continue  # module type changed — skip
                    if new_node.config != prev_node.config:
                        continue  # config changed — skip
                    if new_node.values != prev_node.values:
                        continue  # source/runtime values changed — skip
                    # Check that all edges touching this node are still present
                    prev_node_edges = {
                        e for e in prev_edge_set
                        if e[0] == prev_node.id or e[1] == prev_node.id
                    }
                    if not prev_node_edges.issubset(new_edge_set):
                        continue  # edges changed — skip
                    prev_state = prev_run.nodes.get(prev_node.id)
                    if prev_state is None:
                        continue
                    if prev_state.status not in ("succeeded", "skipped"):
                        continue  # only inherit terminal states
                    inherited_states[prev_node.id] = prev_state
            except (FileNotFoundError, ValueError):
                pass  # ignore missing / corrupt previous run

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
                node.id: (
                    inherited_states[node.id].model_copy(
                        update={"batch_index": batch_index_by_node[node.id]}
                    )
                    if node.id in inherited_states
                    else RunNodeState(
                        node_id=node.id,
                        module_type=node.module_type,
                        batch_index=batch_index_by_node[node.id],
                    )
                )
                for node in execution_graph.nodes
            },
        )
        # When inheriting, update the run status to reflect already-completed
        # nodes so the run is not stuck in 'queued' with completed batches.
        if inherited_states:
            self._refresh_run_status(run)
        return self.run_store.save(run)

    def execute_next_batch(self, run_id: str) -> WorkflowRun:
        with self._execution_lock:
            return self._run_cancellable(run_id, self._execute_next_batch)

    def execute_node(self, run_id: str, node_id: str) -> WorkflowRun:
        """Execute exactly one requested node and invalidate only its descendants."""

        with self._execution_lock:
            return self._run_cancellable(
                run_id,
                lambda active_run_id: self._execute_single_node(
                    active_run_id, node_id
                ),
            )

    def execute_scheduled_node(self, run_id: str, node_id: str) -> WorkflowRun:
        """Execute one orchestration-owned node without invalidating descendants.

        A batch worker compiles each persisted Playground node into a task and
        calls this only after its upstream tasks have completed. The
        existing run document remains the product-facing source of truth.
        """

        with self._execution_lock:
            return self._run_cancellable(
                run_id,
                lambda active_run_id: self._execute_scheduled_node(
                    active_run_id,
                    node_id,
                ),
            )

    def _execute_scheduled_node(self, run_id: str, node_id: str) -> WorkflowRun:
        self._raise_if_cancelled(run_id)
        run = self.run_store.load(run_id)
        graph_nodes = {node.id: node for node in run.graph.nodes}
        node = graph_nodes.get(node_id)
        if node is None:
            raise DagExecutionError(f"실행할 노드를 찾을 수 없습니다: {node_id}")

        state = run.nodes[node_id]
        if state.status in ("succeeded", "skipped"):
            return run
        if state.status in ("failed", "running"):
            # A worker retry or a restarted Job owns this invocation now.
            self._reset_node_state(state)

        batch = run.batches[state.batch_index]
        run.status = "running"
        batch.status = "running"
        batch.started_at = batch.started_at or utc_now_iso()
        batch.completed_at = None
        self.run_store.save_progress(run, node_id)

        should_execute, skip_reason = self._should_execute_node(run, node)
        if not should_execute:
            state.status = "skipped"
            state.outcome = None
            state.skip_reason = skip_reason
            state.completed_at = utc_now_iso()
            self._refresh_run_status(run)
            return self.run_store.save(run)

        try:
            self._execute_node(run, node, state)
        except (DagExecutionCancelled, ModuleWorkerCancelled):
            raise
        except Exception as error:
            state.status = "failed"
            state.outcome = "failed"
            state.error = self._format_error(
                error,
                include_type=not isinstance(
                    error,
                    (DagExecutionError, ValidationError, ModuleExecutionError),
                ),
            )
            state.completed_at = utc_now_iso()
            self._refresh_run_status(run)
            self.run_store.save(run)
            # The batch worker owns retry/failure policy, so preserve it.
            raise

        self._refresh_run_status(run)
        return self.run_store.save(run)

    def _execute_single_node(self, run_id: str, node_id: str) -> WorkflowRun:
        """
        Execute a node and its downstream dependents as a standalone run segment.
        
        Parameters:
            run_id (str): Identifier of the workflow run.
            node_id (str): Identifier of the node to execute.
        
        Returns:
            WorkflowRun: The persisted workflow run after execution.
        
        Raises:
            DagExecutionError: If the node is unknown or cannot currently be executed.
            DagExecutionCancelled: If execution is cancelled.
            ModuleWorkerCancelled: If the execution worker is cancelled.
        """
        self._raise_if_cancelled(run_id)
        run = self.run_store.load(run_id)
        self._recover_interrupted_state(run)
        graph_nodes = {node.id: node for node in run.graph.nodes}
        node = graph_nodes.get(node_id)
        if node is None:
            raise DagExecutionError(f"실행할 노드를 찾을 수 없습니다: {node_id}")

        should_execute, unavailable_reason = self._should_execute_node(run, node)
        if not should_execute:
            raise DagExecutionError(
                f"노드 {node_id}을 단독 실행할 수 없습니다: {unavailable_reason}"
            )

        affected_node_ids = {node_id, *self._descendant_node_ids(run, node_id)}
        for affected_node_id in affected_node_ids:
            self._reset_node_state(run.nodes[affected_node_id])

        state = run.nodes[node_id]
        batch = run.batches[state.batch_index]
        started_at = utc_now_iso()
        run.status = "running"
        batch.status = "running"
        batch.started_at = started_at
        batch.completed_at = None
        self.run_store.save(run)

        try:
            self._execute_node(run, node, state)
        except (DagExecutionCancelled, ModuleWorkerCancelled):
            raise
        except (DagExecutionError, ValidationError, ModuleExecutionError) as error:
            state.status = "failed"
            state.outcome = "failed"
            state.error = self._format_error(error)
            state.completed_at = utc_now_iso()
        except Exception as error:  # keep the run inspectable on unexpected failures
            state.status = "failed"
            state.outcome = "failed"
            state.error = self._format_error(error, include_type=True)
            state.completed_at = utc_now_iso()

        self._refresh_run_status(run)
        return self.run_store.save(run)


    def _execute_next_batch(self, run_id: str) -> WorkflowRun:
        """
        Execute the next incomplete batch of a workflow run.
        
        Returns:
        	WorkflowRun: The updated workflow run after batch execution.
        """
        self._raise_if_cancelled(run_id)
        run = self.run_store.load(run_id)
        self._recover_interrupted_state(run)
        if run.status == "completed":
            return run
        if run.status == "failed":
            raise DagExecutionError(
                "실패한 실행입니다. resume API로 실패 노드를 재시도해 주세요"
            )

        batch = next(
            (candidate for candidate in run.batches if candidate.status != "completed"),
            None,
        )
        if batch is None:
            run.status = "completed"
            return self.run_store.save(run)

        run.status = "running"
        batch.status = "running"
        batch.started_at = batch.started_at or utc_now_iso()
        self.run_store.save(run)

        graph_nodes = {node.id: node for node in run.graph.nodes}
        batch_failed = False
        for node_id in batch.node_ids:
            self._raise_if_cancelled(run_id)
            state = run.nodes[node_id]
            if state.status in ("succeeded", "skipped"):
                continue
            node = graph_nodes[node_id]
            should_execute, skip_reason = self._should_execute_node(run, node)
            if not should_execute:
                state.status = "skipped"
                state.outcome = None
                state.skip_reason = skip_reason
                state.completed_at = utc_now_iso()
                self.run_store.save(run)
                continue
            try:
                self._execute_node(run, node, state)
            except (DagExecutionCancelled, ModuleWorkerCancelled):
                raise
            except (DagExecutionError, ValidationError, ModuleExecutionError) as error:
                state.status = "failed"
                state.outcome = "failed"
                state.error = self._format_error(error)
                state.completed_at = utc_now_iso()
                batch_failed = True
            except Exception as error:  # keep the run inspectable on unexpected failures
                state.status = "failed"
                state.outcome = "failed"
                state.error = self._format_error(error, include_type=True)
                state.completed_at = utc_now_iso()
                batch_failed = True
            self.run_store.save(run)

        batch.completed_at = utc_now_iso()
        if batch_failed:
            batch.status = "failed"
            run.status = "failed"
        else:
            batch.status = "completed"
            run.status = (
                "completed"
                if all(
                    item.status in ("succeeded", "failed", "skipped")
                    for item in run.nodes.values()
                )
                else "queued"
            )
        return self.run_store.save(run)

    def execute_all(self, run_id: str) -> WorkflowRun:
        with self._execution_lock:
            return self._run_cancellable(run_id, self._execute_all)

    def _execute_all(self, run_id: str) -> WorkflowRun:
        run = self.run_store.load(run_id)
        while run.status not in ("completed", "failed"):
            self._raise_if_cancelled(run_id)
            run = self._execute_next_batch(run_id)
        return run

    @staticmethod
    def _reset_node_state(state: RunNodeState) -> None:
        """
        Reset a node state to its initial pending state.
        
        Parameters:
        	state (RunNodeState): The node state to reset.
        """
        state.status = "pending"
        state.input_payload = None
        state.config_payload = {}
        state.output = None
        state.error = None
        state.cache_key = None
        state.cache_hit = False
        state.outcome = None
        state.skip_reason = None
        state.started_at = None
        state.completed_at = None
        state.elapsed_ms = None
        state.cost_usd = None
        state.usage = None
        state.progress = {}

    @staticmethod
    def _descendant_node_ids(run: WorkflowRun, node_id: str) -> Set[str]:
        """Return the identifiers of all nodes downstream from the specified node.
        
        Parameters:
        	run (WorkflowRun): The workflow run containing the graph.
        	node_id (str): The identifier of the starting node.
        
        Returns:
        	Set[str]: The identifiers of all reachable downstream nodes.
        """
        outgoing: Dict[str, List[str]] = defaultdict(list)
        for edge in run.graph.edges:
            outgoing[edge.source].append(edge.target)
        descendants: Set[str] = set()
        pending = list(outgoing[node_id])
        while pending:
            candidate = pending.pop()
            if candidate in descendants:
                continue
            descendants.add(candidate)
            pending.extend(outgoing[candidate])
        return descendants

    @staticmethod
    def _refresh_run_status(run: WorkflowRun) -> None:
        completed_statuses = {"succeeded", "skipped"}
        for batch in run.batches:
            states = [run.nodes[node_id] for node_id in batch.node_ids]
            if any(state.status == "running" for state in states):
                batch.status = "running"
                batch.completed_at = None
            elif any(state.status == "failed" for state in states):
                batch.status = "failed"
                batch.completed_at = utc_now_iso()
            elif all(state.status in completed_statuses for state in states):
                batch.status = "completed"
                batch.completed_at = utc_now_iso()
            else:
                batch.status = "pending"
                batch.completed_at = None

        states = list(run.nodes.values())
        if any(state.status == "running" for state in states):
            run.status = "running"
        elif any(state.status == "failed" for state in states):
            run.status = "failed"
        elif all(state.status in completed_statuses for state in states):
            run.status = "completed"
        else:
            run.status = "queued"

    def resume(self, run_id: str) -> WorkflowRun:
        with self._execution_lock:
            return self._run_cancellable(run_id, self._resume)

    def prepare_resume(self, run_id: str) -> WorkflowRun:
        """Reset failed/paused state and persist it without executing the run.

        External queue consumers use this to make a run claimable again; the
        actual execution is then owned by a separate process or Flow container.
        """

        with self._execution_lock:
            return self._prepare_resume(run_id)

    def request_cancel(self, run_id: str) -> bool:
        """Signal cancellation without waiting for the execution lock."""

        return self._request_cancel(run_id)

    def cancel_run(self, run_id: str) -> WorkflowRun:
        """Signal cancellation before waiting for the execution lock."""

        self._request_cancel(run_id)
        with self._execution_lock:
            try:
                run = self._persist_cancelled_run(run_id)
            finally:
                with self._cancellation_lock:
                    self._cancelled_run_ids.discard(run_id)
            return run

    def clear_runtime_cache(self) -> Dict[str, int]:
        """Clear reusable results and run history without deleting workflows."""

        self._request_cancel_all()
        with self._execution_lock:
            try:
                domain_caches = self.module_registry.clear_caches()
                return {
                    "runs_removed": self.run_store.clear(),
                    "cache_entries_removed": self.result_cache.clear(),
                    **domain_caches,
                }
            finally:
                with self._cancellation_lock:
                    self._cancelled_run_ids.clear()

    def _resume(self, run_id: str) -> WorkflowRun:
        self._prepare_resume(run_id)
        return self._execute_all(run_id)

    def _prepare_resume(self, run_id: str) -> WorkflowRun:
        run = self.run_store.load(run_id)
        failed_node_ids = {
            node_id
            for node_id, state in run.nodes.items()
            if state.status == "failed"
        }
        for node_id in failed_node_ids:
            state = run.nodes[node_id]
            state.status = "pending"
            state.error = None
            state.outcome = None
            state.skip_reason = None
            state.started_at = None
            state.completed_at = None
        for batch in run.batches:
            if any(node_id in failed_node_ids for node_id in batch.node_ids):
                batch.status = "pending"
                batch.started_at = None
                batch.completed_at = None
        if run.status not in ("completed",):
            run.status = "queued"
        return self.run_store.save(run)

    def _execute_node(
        self,
        run: WorkflowRun,
        node: WorkflowNode,
        state: RunNodeState,
    ) -> None:
        """
        Execute a workflow node, recording its input, output, status, cache state, progress, usage, and cost.
        
        Parameters:
            run (WorkflowRun): The workflow run containing the node.
            node (WorkflowNode): The node to execute.
            state (RunNodeState): The node state to update with execution results.
        """
        input_payload = self._assemble_input(run, node)
        module = self.module_registry.get(node.module_type)
        validated_config = module.validate_config(node.config).model_dump(mode="json")
        cache_payload = module.cache_payload(input_payload, validated_config)
        cache_key = self.result_cache.key(
            f"{node.module_type}@{module.definition.version}", cache_payload
        )

        import time
        from backend.providers.llm.cost import calculate_openai_cost

        t_start = time.perf_counter()
        state.status = "running"
        state.input_payload = compact_history_value(input_payload)
        state.config_payload = compact_history_value(validated_config)
        state.error = None
        state.skip_reason = None
        state.outcome = None
        state.cache_key = cache_key
        state.cache_hit = False
        state.progress = {}
        state.started_at = utc_now_iso()
        self.run_store.save_progress(run, node.id)

        last_progress_persisted_at = 0.0
        last_progress_phase: Any = None

        def persist_progress(progress: Dict[str, Any]) -> None:
            """Persist throttled live progress independently from large outputs."""

            nonlocal last_progress_persisted_at, last_progress_phase
            self._raise_if_cancelled(run.id)
            compact_progress = compact_history_value(progress)
            state.progress = compact_progress
            now = time.monotonic()
            phase = compact_progress.get("phase")
            completed_total_pairs = (
                ("completed_batches", "total_batches"),
                ("completed_items", "total_items"),
                ("completed_sheets", "total_sheets"),
                ("completed_tables", "total_tables"),
            )
            is_final = any(
                isinstance(compact_progress.get(completed_key), (int, float))
                and isinstance(compact_progress.get(total_key), (int, float))
                and compact_progress[total_key] > 0
                and compact_progress[completed_key] >= compact_progress[total_key]
                for completed_key, total_key in completed_total_pairs
            )
            should_persist = (
                last_progress_persisted_at == 0.0
                or phase != last_progress_phase
                or is_final
                or now - last_progress_persisted_at >= 1.0
            )
            if should_persist:
                self.run_store.save_progress(run, node.id)
                last_progress_persisted_at = now
                last_progress_phase = phase

        output: Any = None
        cache_enabled = run.use_cache and module.definition.cacheable and (
            run.cache_only_module_types is None or node.module_type in run.cache_only_module_types
        )
        if cache_enabled:
            output = self.result_cache.get(cache_key)
            state.cache_hit = output is not None
        if output is None:
            self._raise_if_cancelled(run.id)
            if self._module_worker is None:
                module.set_progress_callback(persist_progress)
                try:
                    output = self.module_registry.execute(
                        node.module_type,
                        input_payload,
                        validated_config,
                    )
                finally:
                    module.set_progress_callback(None)
            else:
                output = self._module_worker.execute(
                    node.module_type,
                    input_payload,
                    validated_config,
                    run.id,
                    progress_callback=persist_progress,
                )
            self._raise_if_cancelled(run.id)
            if cache_enabled:
                self.result_cache.put(cache_key, output)

        branch_ports = set(module.definition.branch_outputs.values())
        if module.definition.raw_output:
            missing_outputs: List[str] = []
        elif not isinstance(output, Mapping):
            raise DagExecutionError(
                f"모듈 {node.module_type}이 이름 있는 출력 객체를 반환하지 않았습니다"
            )
        else:
            missing_outputs = (
                []
                if branch_ports.intersection(output)
                else list(branch_ports)
            ) if branch_ports else [
                port for port in module.definition.outputs if port not in output
            ]
        if missing_outputs:
            raise DagExecutionError(
                f"모듈 {node.module_type}이 출력 포트를 생성하지 않았습니다: "
                + ", ".join(missing_outputs)
            )

        t_elapsed = round((time.perf_counter() - t_start) * 1000, 2)
        state.output = output
        state.status = "succeeded"
        state.outcome = module.execution_outcome(output, state.cache_hit)
        state.completed_at = utc_now_iso()
        state.elapsed_ms = t_elapsed

        # Calculate cost & token usage metrics
        node_cost: Optional[float] = None
        node_usage: Optional[Dict[str, int]] = None

        if isinstance(output, Mapping):
            if "answer_json" in output and isinstance(output["answer_json"], Mapping):
                aj = output["answer_json"]
                node_cost = aj.get("estimated_cost_usd")
                if isinstance(aj.get("api_usage"), Mapping):
                    node_usage = {k: int(v) for k, v in aj["api_usage"].items() if v is not None}
            elif "semantic_match" in output and isinstance(output["semantic_match"], Mapping):
                metrics = output["semantic_match"].get("metrics") or {}
                raw_usage = metrics.get("api_usage") or {}
                if isinstance(raw_usage, Mapping):
                    node_usage = {k: int(v) for k, v in raw_usage.items() if v is not None}
                node_cost = metrics.get("estimated_cost_usd")
            elif "usage" in output or "_usage" in output:
                raw_u = output.get("usage") or output.get("_usage")
                model_used = output.get("model") or validated_config.get("model") or ""
                if isinstance(raw_u, Mapping):
                    node_usage = {
                        "prompt_tokens": int(raw_u.get("prompt_tokens", 0) or 0),
                        "completion_tokens": int(raw_u.get("completion_tokens", 0) or 0),
                        "cached_tokens": int(raw_u.get("cached_tokens", 0) or 0),
                        "total_tokens": int(raw_u.get("total_tokens", 0) or 0),
                    }
                    node_cost = calculate_openai_cost(
                        model_name=str(model_used),
                        prompt_tokens=node_usage["prompt_tokens"],
                        completion_tokens=node_usage["completion_tokens"],
                        cached_tokens=node_usage["cached_tokens"],
                    )

        worker_metadata = (
            getattr(self._module_worker, "last_metadata", {})
            if self._module_worker is not None and not state.cache_hit
            else {}
        )
        module_usage = (
            getattr(module, "last_usage", None) if not state.cache_hit else None
        )
        raw_u = (
            module_usage
            if isinstance(module_usage, Mapping)
            else worker_metadata.get("usage")
            if isinstance(worker_metadata, Mapping)
            else None
        )
        if node_usage is None and isinstance(raw_u, Mapping):
            model_used = (
                getattr(module, "last_model", "")
                or (
                    worker_metadata.get("model", "")
                    if isinstance(worker_metadata, Mapping)
                    else ""
                )
                or validated_config.get("model")
                or ""
            )
            node_usage = {
                "prompt_tokens": int(raw_u.get("prompt_tokens", 0) or 0),
                "completion_tokens": int(raw_u.get("completion_tokens", 0) or 0),
                "cached_tokens": int(raw_u.get("cached_tokens", 0) or 0),
                "total_tokens": int(raw_u.get("total_tokens", 0) or 0),
            }
            if node_usage.get("total_tokens", 0) > 0:
                node_cost = calculate_openai_cost(
                    model_name=str(model_used),
                    prompt_tokens=node_usage["prompt_tokens"],
                    completion_tokens=node_usage["completion_tokens"],
                    cached_tokens=node_usage["cached_tokens"],
                )

        state.cost_usd = node_cost
        state.usage = node_usage
        self.run_store.save(run)

    def _run_cancellable(self, run_id: str, operation) -> WorkflowRun:
        with self._cancellation_lock:
            self._cancelled_run_ids.discard(run_id)
            self._active_run_ids.add(run_id)
        try:
            return operation(run_id)
        except (DagExecutionCancelled, ModuleWorkerCancelled) as error:
            self._persist_cancelled_run(run_id)
            raise DagExecutionCancelled("실행이 사용자 요청으로 중단되었습니다") from error
        finally:
            with self._cancellation_lock:
                self._active_run_ids.discard(run_id)

    def _request_cancel(self, run_id: str) -> bool:
        with self._cancellation_lock:
            is_active = run_id in self._active_run_ids
            if is_active:
                self._cancelled_run_ids.add(run_id)
        worker_cancelled = (
            bool(self._module_worker.cancel(run_id))
            if self._module_worker is not None
            else False
        )
        return is_active or worker_cancelled

    def _request_cancel_all(self) -> None:
        with self._cancellation_lock:
            active_run_ids = set(self._active_run_ids)
            self._cancelled_run_ids.update(active_run_ids)
        if self._module_worker is not None:
            self._module_worker.reset()

    def _raise_if_cancelled(self, run_id: str) -> None:
        with self._cancellation_lock:
            cancelled = run_id in self._cancelled_run_ids
        if not cancelled:
            try:
                cancelled = self.run_store.is_cancel_requested(run_id)
            except Exception:
                logger.warning(
                    "DB cancellation 상태 조회 실패 (run_id=%s)",
                    run_id,
                    exc_info=True,
                )
        if cancelled:
            raise DagExecutionCancelled("실행이 사용자 요청으로 중단되었습니다")

    def _persist_cancelled_run(self, run_id: str) -> WorkflowRun:
        """Persist a run after cancellation, resetting running nodes and marking non-terminal runs as paused.
        
        Parameters:
        	run_id (str): Identifier of the run to persist.
        
        Returns:
        	WorkflowRun: The saved run with updated node and execution statuses.
        """
        run = self.run_store.load(run_id)
        was_terminal = run.status in ("completed", "failed")
        for state in run.nodes.values():
            if state.status == "running":
                self._reset_node_state(state)
        self._refresh_run_status(run)
        if not was_terminal and run.status not in ("completed", "failed"):
            run.status = "paused"
        return self.run_store.save(run)

    def _should_execute_node(
        self, run: WorkflowRun, node: WorkflowNode
    ) -> Tuple[bool, Optional[str]]:
        """
        Determine whether a node has all prerequisites required for execution.
        
        Parameters:
            run (WorkflowRun): Workflow run containing the node's inputs and incoming edges.
            node (WorkflowNode): Node whose execution prerequisites are evaluated.
        
        Returns:
            Tuple[bool, Optional[str]]: Whether the node can execute and, when it cannot, the reason it will be skipped.
        """
        incoming_edges = [edge for edge in run.graph.edges if edge.target == node.id]
        if not incoming_edges:
            module = self.module_registry.get(node.module_type)
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
            _, target_input = self._resolve_ports(edge, node_by_id)
            edges_by_input[target_input].append(edge)

        module = self.module_registry.get(node.module_type)
        supplied_inputs = (
            set(node.values)
            | set(run.runtime_inputs.get(node.id, {}))
            | set(edges_by_input)
        )
        missing_inputs = [
            port for port in module.definition.inputs if port not in supplied_inputs
        ]
        if missing_inputs:
            return (
                False,
                "연결되지 않은 필수 입력이 있어 건너뜁니다: "
                + ", ".join(missing_inputs),
            )

        for target_input, alternatives in edges_by_input.items():
            if not any(self._edge_is_active(run, edge) for edge in alternatives):
                return (
                    False,
                    f"입력 {target_input}에 활성화된 분기 출력이 없어 건너뜁니다",
                )
        return True, None

    @staticmethod
    def _edge_is_active(run: WorkflowRun, edge: WorkflowEdge) -> bool:
        source_state = run.nodes[edge.source]
        if edge.source_branch is None:
            return source_state.status == "succeeded"
        return source_state.outcome == edge.source_branch

    def _assemble_input(
        self, run: WorkflowRun, node: WorkflowNode
    ) -> Any:
        payload = dict(node.values)
        target_module = self.module_registry.get(node.module_type)
        payload.update(run.runtime_inputs.get(node.id, {}))
        node_by_id = {item.id: item for item in run.graph.nodes}
        incoming_edges = [edge for edge in run.graph.edges if edge.target == node.id]
        edges_by_input: Dict[str, List[Tuple[WorkflowEdge, str]]] = defaultdict(list)
        for edge in incoming_edges:
            source_output, target_input = self._resolve_ports(edge, node_by_id)
            edges_by_input[target_input].append((edge, source_output))

        for target_input, alternatives in edges_by_input.items():
            active_edges = [
                (edge, source_output)
                for edge, source_output in alternatives
                if self._edge_is_active(run, edge)
            ]
            if len(active_edges) != 1:
                raise DagExecutionError(
                    f"노드 {node.id}의 입력 {target_input}에 활성 분기가 {len(active_edges)}개입니다"
                )
            edge, source_output = active_edges[0]
            source_state = run.nodes[edge.source]
            if source_state.status != "succeeded":
                raise DagExecutionError(
                    f"선행 노드 {edge.source}의 출력이 아직 준비되지 않았습니다"
                )
            source_module = self.module_registry.get(
                node_by_id[edge.source].module_type
            ).definition
            if source_module.raw_output:
                source_value = source_state.output
            else:
                if not isinstance(source_state.output, Mapping) or source_output not in source_state.output:
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

    def _resolve_ports(
        self,
        edge: WorkflowEdge,
        node_by_id: Mapping[str, WorkflowNode],
    ) -> Tuple[str, str]:
        source_module = self.module_registry.get(
            node_by_id[edge.source].module_type
        ).definition
        target_module = self.module_registry.get(
            node_by_id[edge.target].module_type
        ).definition

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
                raise DagExecutionError(
                    f"연결 {edge.id}의 source_output을 지정해야 합니다"
                )
            source_output = source_module.outputs[0]
        if source_output not in source_module.outputs:
            raise DagExecutionError(
                f"모듈 {source_module.type}에 출력 포트 {source_output}이 없습니다"
            )

        target_input = edge.target_input
        if target_input is None:
            if len(target_module.inputs) != 1:
                raise DagExecutionError(
                    f"연결 {edge.id}의 target_input을 지정해야 합니다"
                )
            target_input = target_module.inputs[0]
        if target_input not in target_module.inputs:
            raise DagExecutionError(
                f"모듈 {target_module.type}에 입력 포트 {target_input}이 없습니다"
            )
        return source_output, target_input

    def _recover_interrupted_state(self, run: WorkflowRun) -> None:
        """Restore interrupted workflow execution state to pending or queued status and persist the changes."""
        changed = False
        for state in run.nodes.values():
            if state.status == "running":
                state.status = "pending"
                state.error = None
                state.outcome = None
                state.skip_reason = None
                changed = True
        for batch in run.batches:
            if batch.status == "running":
                batch.status = "pending"
                changed = True
        if run.status == "running":
            run.status = "queued"
            changed = True
        if changed:
            self.run_store.save(run)

    @staticmethod
    def _format_error(error: Exception, *, include_type: bool = False) -> str:
        """
        Format an exception into a concise, user-facing error message.
        
        Parameters:
            error (Exception): The exception to format.
            include_type (bool): Whether to prefix ordinary error messages with the exception type.
        
        Returns:
            str: The formatted error message, truncated to 4,000 characters when necessary.
        """
        if isinstance(error, ValidationError):
            messages = [
                f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
                for item in error.errors(include_url=False)
            ]
            message = "; ".join(messages)
        else:
            message = str(error)
            for marker in ("\n[SQL:", " [SQL:"):
                if marker in message:
                    message = message.split(marker, 1)[0].rstrip()
                    break
            if include_type:
                message = f"{type(error).__name__}: {message}"
        if len(message) > 4000:
            return message[:4000].rstrip() + "…"
        return message
