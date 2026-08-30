import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from threading import Lock, RLock
from typing import Any, Callable, Dict, List, Mapping, Optional, Set, Tuple
from uuid import uuid4

from pydantic import ValidationError

from backend.core.telemetry import trace_node_execution
from backend.engine.runtime.registry_base import BaseModuleRegistry
from backend.providers.openai_pricing import calculate_openai_cost
from modules.common.base_module import BaseModule, ModuleExecutionError

from .history import compact_history_value
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
from .store import ResultCache, RunStore

logger = logging.getLogger(__name__)


@dataclass
class _PreparedNodeExecution:
    input_payload: Any
    module: BaseModule
    validated_config: Dict[str, Any]
    cache_key: str
    cache_enabled: bool
    output: Any
    started_at: float
    progress_callback: Callable[[Dict[str, Any]], None]


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
    ) -> None:
        self.module_registry = module_registry
        self.run_store = run_store
        self.result_cache = result_cache
        self._execution_lock = RLock()
        self._cancellation_lock = Lock()
        self._active_run_ids: Set[str] = set()
        self._cancelled_run_ids: Set[str] = set()

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
                    f"노드 {node.id}의 config가 유효하지 않습니다: " + self._format_error(error)
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

        import networkx as nx

        edge_ids: Set[str] = set()
        occupied_inputs: Dict[Tuple[str, str], List[WorkflowEdge]] = defaultdict(list)
        graph_dag = nx.DiGraph()
        for node in graph.nodes:
            graph_dag.add_node(node.id)

        for edge in graph.edges:
            if edge.id in edge_ids:
                raise DagExecutionError(f"중복 연결 ID입니다: {edge.id}")
            edge_ids.add(edge.id)
            if edge.source not in node_by_id or edge.target not in node_by_id:
                raise DagExecutionError(f"연결 {edge.id}이 존재하지 않는 노드를 참조합니다")
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
            graph_dag.add_edge(edge.source, edge.target)

        if not nx.is_directed_acyclic_graph(graph_dag):
            try:
                cycle = nx.find_cycle(graph_dag, orientation="original")
                cycle_str = " -> ".join([u for u, v, _ in cycle] + [cycle[0][0]])
                raise DagExecutionError(f"순환 연결이 감지되었습니다: {cycle_str}")
            except DagExecutionError:
                raise
            except Exception:
                raise DagExecutionError("순환 연결이 감지되었습니다")

        batches: List[List[str]] = [
            list(generation) for generation in nx.topological_generations(graph_dag)
        ]
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
            request (WorkflowExecutionRequest): Runtime inputs, configuration overrides, and cache settings.

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
                "실행 입력이 존재하지 않는 노드를 참조합니다: " + ", ".join(unknown_inputs)
            )
        unknown_config_nodes = sorted(set(request.config_overrides) - known_nodes)
        if unknown_config_nodes:
            raise DagExecutionError(
                "실행 설정이 존재하지 않는 노드를 참조합니다: " + ", ".join(unknown_config_nodes)
            )

        for node in execution_graph.nodes:
            override = request.config_overrides.get(node.id)
            if override:
                node.config = {**node.config, **override}

        batches = self.validate_graph(execution_graph)
        for node_id, runtime_input in request.inputs.items():
            node = next(item for item in execution_graph.nodes if item.id == node_id)
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
        return self.run_store.save(run)

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

    def execute_scheduled_batch(
        self,
        run_id: str,
        node_ids: tuple[str, ...],
    ) -> WorkflowRun:
        """Execute one topological generation through an asyncio TaskGroup."""
        return asyncio.run(self.execute_scheduled_batch_async(run_id, node_ids))

    async def execute_scheduled_batch_async(
        self,
        run_id: str,
        node_ids: tuple[str, ...],
    ) -> WorkflowRun:
        """Run isolated node snapshots concurrently and merge terminal states once."""
        if not node_ids:
            raise DagExecutionError("실행할 batch 노드가 없습니다")
        if len(set(node_ids)) != len(node_ids):
            raise DagExecutionError("batch에 중복 노드 ID가 있습니다")

        with self._cancellation_lock:
            self._cancelled_run_ids.discard(run_id)
            self._active_run_ids.add(run_id)
        try:
            base_run, selected_nodes = await asyncio.to_thread(
                self._prepare_scheduled_batch,
                run_id,
                node_ids,
            )

            module_locks: dict[str, asyncio.Lock] = {}
            results: dict[str, RunNodeState] = {}
            errors: dict[str, Exception] = {}

            async def execute_isolated(node: WorkflowNode) -> None:
                snapshot = base_run.model_copy(deep=True)
                state = snapshot.nodes[node.id]
                if state.status in ("succeeded", "skipped"):
                    results[node.id] = state
                    return
                if state.status in ("failed", "running"):
                    self._reset_node_state(state)
                should_execute, skip_reason = self._should_execute_node(snapshot, node)
                if not should_execute:
                    state.status = "skipped"
                    state.outcome = None
                    state.skip_reason = skip_reason
                    state.completed_at = utc_now_iso()
                    results[node.id] = state
                    return

                module = self.module_registry.get(node.module_type)
                policy = module.definition.task or module.definition.task_policy
                module_lock = module_locks.setdefault(node.module_type, asyncio.Lock())
                for attempt in range(policy.retries + 1):
                    try:
                        async with module_lock:
                            await self._execute_node_async(
                                snapshot,
                                node,
                                state,
                                False,
                            )
                        results[node.id] = state
                        return
                    except DagExecutionCancelled as error:
                        errors[node.id] = error
                        return
                    except Exception as error:
                        if attempt >= policy.retries:
                            state.status = "failed"
                            state.outcome = "failed"
                            state.error = self._format_error(
                                error,
                                include_type=not isinstance(
                                    error,
                                    (
                                        DagExecutionError,
                                        ValidationError,
                                        ModuleExecutionError,
                                    ),
                                ),
                            )
                            state.completed_at = utc_now_iso()
                            results[node.id] = state
                            errors[node.id] = error
                            return
                        self._reset_node_state(state)
                        if policy.retry_delay_seconds:
                            await asyncio.sleep(policy.retry_delay_seconds)

            async with asyncio.TaskGroup() as task_group:
                for node in selected_nodes:
                    task_group.create_task(
                        execute_isolated(node),
                        name=f"workflow:{run_id}:{node.id}",
                    )

            merged = await asyncio.to_thread(
                self._merge_scheduled_batch_results,
                run_id,
                node_ids,
                results,
            )

            cancellation = next(
                (error for error in errors.values() if isinstance(error, DagExecutionCancelled)),
                None,
            )
            if cancellation is not None:
                await asyncio.to_thread(self._persist_cancelled_run, run_id)
                raise DagExecutionCancelled(
                    "실행이 사용자 요청으로 중단되었습니다"
                ) from cancellation
            if errors:
                failed_nodes = ", ".join(sorted(errors))
                first_error = errors[sorted(errors)[0]]
                raise DagExecutionError(f"batch 노드 실행 실패: {failed_nodes}") from first_error
            return merged
        finally:
            with self._cancellation_lock:
                self._active_run_ids.discard(run_id)

    def _prepare_scheduled_batch(
        self,
        run_id: str,
        node_ids: tuple[str, ...],
    ) -> tuple[WorkflowRun, tuple[WorkflowNode, ...]]:
        """Validate a batch and persist its live node states before execution.

        Scheduled TaskGroup nodes execute against isolated snapshots. Persisting
        their ``running`` transition here keeps the API/SSE projection live while
        a worker is waiting for a module response instead of jumping directly
        from ``pending`` to a terminal state.
        """
        with self._execution_lock:
            run = self.run_store.load(run_id)
            graph_nodes = {node.id: node for node in run.graph.nodes}
            try:
                selected_nodes = tuple(graph_nodes[node_id] for node_id in node_ids)
            except KeyError as error:
                raise DagExecutionError(
                    f"실행할 노드를 찾을 수 없습니다: {error.args[0]}"
                ) from error
            batch_indexes = {run.nodes[node.id].batch_index for node in selected_nodes}
            if len(batch_indexes) != 1:
                raise DagExecutionError("TaskGroup은 하나의 topological batch만 실행할 수 있습니다")
            batch = run.batches[next(iter(batch_indexes))]
            if set(node_ids) != set(batch.node_ids):
                raise DagExecutionError(
                    "TaskGroup 입력은 persisted batch의 전체 노드와 일치해야 합니다"
                )
            run.status = "running"
            batch.status = "running"
            batch.started_at = batch.started_at or utc_now_iso()
            batch.completed_at = None

            started_at = utc_now_iso()
            for node in selected_nodes:
                state = run.nodes[node.id]
                if state.status in ("succeeded", "skipped"):
                    continue
                if state.status in ("failed", "running"):
                    self._reset_node_state(state)
                should_execute, skip_reason = self._should_execute_node(run, node)
                if should_execute:
                    state.status = "running"
                    state.started_at = started_at
                    state.completed_at = None
                    state.error = None
                    state.skip_reason = None
                else:
                    state.status = "skipped"
                    state.outcome = None
                    state.skip_reason = skip_reason
                    state.completed_at = started_at

            self._refresh_run_status(run)
            for node in selected_nodes:
                state = run.nodes[node.id]
                if state.status == "running":
                    self.run_store.save_progress(run, node.id)
                elif state.status == "skipped":
                    self.run_store.save_node(run, node.id)
            return run, selected_nodes

    def _merge_scheduled_batch_results(
        self,
        run_id: str,
        node_ids: tuple[str, ...],
        results: Mapping[str, RunNodeState],
    ) -> WorkflowRun:
        """Merge and persist one async batch while holding the execution lock."""
        with self._execution_lock:
            merged = self.run_store.load(run_id)
            for node_id in node_ids:
                merged.nodes[node_id] = results[node_id]
            self._refresh_run_status(merged)
            for node_id in node_ids:
                self.run_store.save_node(merged, node_id)
            return merged

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
            return self.run_store.save_node(run, node_id)

        try:
            self._execute_node(run, node, state)
        except DagExecutionCancelled:
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
            self.run_store.save_node(run, node_id)
            # The batch worker owns retry/failure policy, so preserve it.
            raise

        self._refresh_run_status(run)
        return self.run_store.save_node(run, node_id)

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
            source_node_ids = {edge.source for edge in run.graph.edges}
            sink_node_ids = set(run.nodes) - source_node_ids
            run.status = (
                "completed"
                if any(run.nodes[node_id].status == "succeeded" for node_id in sink_node_ids)
                else "failed"
            )
        else:
            # A claimed worker remains the owner between node transitions.
            # Returning to ``queued`` here makes KEDA count the live run as new
            # backlog and creates an unnecessary no-op Job.
            run.status = "running" if run.status == "running" else "queued"

    def prepare_resume(self, run_id: str) -> WorkflowRun:
        """Reset failed/paused state and persist it without executing the run.

        External queue consumers use this to make a run claimable again; the
        actual execution is then owned by a separate process or Flow container.
        """

        with self._execution_lock:
            self.run_store.clear_cancel_request(run_id)
            with self._cancellation_lock:
                self._cancelled_run_ids.discard(run_id)
            return self._prepare_resume(run_id)

    def request_cancel(self, run_id: str) -> bool:
        """Signal cancellation without waiting for the execution lock."""

        return self._request_cancel(run_id)

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

    def _prepare_resume(self, run_id: str) -> WorkflowRun:
        run = self.run_store.load(run_id)
        failed_node_ids = {
            node_id for node_id, state in run.nodes.items() if state.status == "failed"
        }
        reset_node_ids = set(failed_node_ids)

        # Kubernetes executes one topological generation as a parallel batch.
        # When one task fails, the scheduler can mark still-runnable siblings as
        # skipped. They and their non-terminal descendants must be made
        # claimable again, otherwise a resumed run can finish without producing
        # its terminal output.
        for batch in run.batches:
            if any(node_id in failed_node_ids for node_id in batch.node_ids):
                reset_node_ids.update(
                    node_id
                    for node_id in batch.node_ids
                    if run.nodes[node_id].status != "succeeded"
                )

        outgoing: Dict[str, Set[str]] = defaultdict(set)
        for edge in run.graph.edges:
            outgoing[edge.source].add(edge.target)
        pending_ancestors = list(reset_node_ids)
        while pending_ancestors:
            node_id = pending_ancestors.pop()
            for descendant_id in outgoing.get(node_id, set()):
                descendant = run.nodes[descendant_id]
                if descendant_id not in reset_node_ids and descendant.status != "succeeded":
                    reset_node_ids.add(descendant_id)
                    pending_ancestors.append(descendant_id)

        for node_id in reset_node_ids:
            self._reset_node_state(run.nodes[node_id])
        for batch in run.batches:
            if any(node_id in reset_node_ids for node_id in batch.node_ids):
                batch.status = "pending"
                batch.started_at = None
                batch.completed_at = None
        if reset_node_ids:
            self._refresh_run_status(run)
        return self.run_store.save(run)

    def _execute_node(
        self,
        run: WorkflowRun,
        node: WorkflowNode,
        state: RunNodeState,
        persist_progress_updates: bool = True,
    ) -> None:
        """Execute one node through the synchronous compatibility boundary."""
        prepared = self._prepare_node_execution(
            run,
            node,
            state,
            persist_progress_updates,
        )
        output = prepared.output
        if output is None:
            self._raise_if_cancelled(run.id)
            with trace_node_execution(
                run.workflow_id,
                run.id,
                node.id,
                node.module_type,
                state.batch_index,
            ) as _span:
                prepared.module.set_progress_callback(prepared.progress_callback)
                try:
                    output = self.module_registry.execute(
                        node.module_type,
                        prepared.input_payload,
                        prepared.validated_config,
                    )
                finally:
                    prepared.module.set_progress_callback(None)
            self._raise_if_cancelled(run.id)
            if prepared.cache_enabled:
                self.result_cache.put(prepared.cache_key, output)
        self._complete_node_execution(run, node, state, prepared, output)

    async def _execute_node_async(
        self,
        run: WorkflowRun,
        node: WorkflowNode,
        state: RunNodeState,
        persist_progress_updates: bool = True,
    ) -> None:
        """Execute one node through its native async hook when available."""
        prepared = await asyncio.to_thread(
            self._prepare_node_execution,
            run,
            node,
            state,
            persist_progress_updates,
        )
        output = prepared.output
        if output is None:
            await self._raise_if_cancelled_async(run.id)
            with trace_node_execution(
                run.workflow_id,
                run.id,
                node.id,
                node.module_type,
                state.batch_index,
            ) as _span:
                prepared.module.set_progress_callback(prepared.progress_callback)
                try:
                    output = await self.module_registry.execute_async(
                        node.module_type,
                        prepared.input_payload,
                        prepared.validated_config,
                    )
                finally:
                    prepared.module.set_progress_callback(None)
            await self._raise_if_cancelled_async(run.id)
            if prepared.cache_enabled:
                await asyncio.to_thread(
                    self.result_cache.put,
                    prepared.cache_key,
                    output,
                )
        self._complete_node_execution(run, node, state, prepared, output)

    def _prepare_node_execution(
        self,
        run: WorkflowRun,
        node: WorkflowNode,
        state: RunNodeState,
        persist_progress_updates: bool,
    ) -> _PreparedNodeExecution:
        """Validate input, initialize state, and resolve a possible cache hit."""
        input_payload = self._assemble_input(run, node)
        module = self.module_registry.get(node.module_type)
        validated_config = module.validate_config(node.config).model_dump(mode="json")
        cache_payload = {
            "input": module.input_model.model_validate(input_payload).model_dump(mode="json"),
            "config": validated_config,
        }
        cache_key = self.result_cache.key(
            f"{node.module_type}@{module.definition.version}", cache_payload
        )

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
        if persist_progress_updates:
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
            if should_persist and persist_progress_updates:
                self.run_store.save_progress(run, node.id)
                last_progress_persisted_at = now
                last_progress_phase = phase

        output: Any = None
        cache_enabled = (
            run.use_cache
            and module.definition.cacheable
            and (
                run.cache_only_module_types is None
                or node.module_type in run.cache_only_module_types
            )
        )
        if cache_enabled:
            output = self.result_cache.get(cache_key)
            state.cache_hit = output is not None
        return _PreparedNodeExecution(
            input_payload=input_payload,
            module=module,
            validated_config=validated_config,
            cache_key=cache_key,
            cache_enabled=cache_enabled,
            output=output,
            started_at=t_start,
            progress_callback=persist_progress,
        )

    def _complete_node_execution(
        self,
        run: WorkflowRun,
        node: WorkflowNode,
        state: RunNodeState,
        prepared: _PreparedNodeExecution,
        output: Any,
    ) -> None:
        """Apply output contracts and terminal usage metrics identically for both paths."""
        del run
        module = prepared.module
        validated_config = prepared.validated_config
        branch_ports = set(module.definition.branch_outputs.values())
        if module.definition.raw_output:
            missing_outputs: List[str] = []
        elif not isinstance(output, Mapping):
            raise DagExecutionError(
                f"모듈 {node.module_type}이 이름 있는 출력 객체를 반환하지 않았습니다"
            )
        else:
            missing_outputs = (
                ([] if branch_ports.intersection(output) else list(branch_ports))
                if branch_ports
                else [port for port in module.definition.outputs if port not in output]
            )
        if missing_outputs:
            raise DagExecutionError(
                f"모듈 {node.module_type}이 출력 포트를 생성하지 않았습니다: "
                + ", ".join(missing_outputs)
            )

        t_elapsed = round((time.perf_counter() - prepared.started_at) * 1000, 2)
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
            elif isinstance(output.get("metrics"), Mapping):
                metrics = output["metrics"]
                raw_usage = metrics.get("api_usage") or {}
                if isinstance(raw_usage, Mapping) and raw_usage:
                    node_usage = {
                        key: int(value) for key, value in raw_usage.items() if value is not None
                    }
                elif metrics.get("total_tokens") is not None:
                    total_tokens = int(metrics.get("total_tokens") or 0)
                    node_usage = {
                        "prompt_tokens": total_tokens,
                        "completion_tokens": 0,
                        "cached_tokens": 0,
                        "total_tokens": total_tokens,
                    }
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

        module_usage = getattr(module, "last_usage", None) if not state.cache_hit else None
        raw_u = module_usage if isinstance(module_usage, Mapping) else None
        if node_usage is None and isinstance(raw_u, Mapping):
            model_used = getattr(module, "last_model", "") or validated_config.get("model") or ""
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

    def _run_cancellable(self, run_id: str, operation) -> WorkflowRun:
        with self._cancellation_lock:
            self._cancelled_run_ids.discard(run_id)
            self._active_run_ids.add(run_id)
        try:
            return operation(run_id)
        except DagExecutionCancelled as error:
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
        return is_active

    def _request_cancel_all(self) -> None:
        with self._cancellation_lock:
            active_run_ids = set(self._active_run_ids)
            self._cancelled_run_ids.update(active_run_ids)

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

    async def _raise_if_cancelled_async(self, run_id: str) -> None:
        """Check durable cancellation state without blocking the event loop."""
        await asyncio.to_thread(self._raise_if_cancelled, run_id)

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
            supplied_fields = set(node.values) | set(run.runtime_inputs.get(node.id, {}))
            required_inputs = (
                list(module.definition.inputs)
                if module.definition.raw_input
                else module.required_input_fields
            )
            missing_inputs = [field for field in required_inputs if field not in supplied_fields]
            if missing_inputs:
                return (
                    False,
                    "연결되지 않은 필수 입력이 있어 건너뜁니다: " + ", ".join(missing_inputs),
                )
            return True, None

        node_by_id = {item.id: item for item in run.graph.nodes}
        edges_by_input: Dict[str, List[WorkflowEdge]] = defaultdict(list)
        for edge in incoming_edges:
            _, target_input = self._resolve_ports(edge, node_by_id)
            edges_by_input[target_input].append(edge)

        module = self.module_registry.get(node.module_type)
        supplied_inputs = (
            set(node.values) | set(run.runtime_inputs.get(node.id, {})) | set(edges_by_input)
        )
        # A raw object connected to the conventional ``input`` port is merged
        # into a structured target DTO by ``_assemble_input``.  Account for the
        # source DTO fields here as well; otherwise a valid typed-object edge is
        # incorrectly skipped before input assembly can validate it.
        if not module.definition.raw_input:
            for target_input, alternatives in edges_by_input.items():
                if target_input != "input":
                    continue
                for edge in alternatives:
                    source_node = node_by_id[edge.source]
                    source_module = self.module_registry.get(source_node.module_type)
                    if source_module.definition.raw_output:
                        supplied_inputs.update(source_module.output_model.model_fields)
        missing_inputs = [
            field for field in module.required_input_fields if field not in supplied_inputs
        ]
        if missing_inputs:
            return (
                False,
                "연결되지 않은 필수 입력이 있어 건너뜁니다: " + ", ".join(missing_inputs),
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

    def _assemble_input(self, run: WorkflowRun, node: WorkflowNode) -> Any:
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
            source_module = self.module_registry.get(node_by_id[edge.source].module_type).definition
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

    def _resolve_ports(
        self,
        edge: WorkflowEdge,
        node_by_id: Mapping[str, WorkflowNode],
    ) -> Tuple[str, str]:
        source_module = self.module_registry.get(node_by_id[edge.source].module_type).definition
        target_module = self.module_registry.get(node_by_id[edge.target].module_type).definition

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
