import asyncio
import logging
from threading import Lock, RLock
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple

from pydantic import ValidationError

from backend.domains.workflow.application import (
    WorkflowGraphValidator,
    WorkflowInputAssembler,
    WorkflowPortResolver,
    WorkflowResultCache,
    WorkflowRunRepository,
)
from backend.domains.workflow.application.resume_planning import WorkflowResumePlanner
from backend.domains.workflow.application.run_creation import WorkflowRunFactory
from backend.domains.workflow.domain import (
    DagExecutionCancelled,
    DagExecutionError,
    WorkflowRunStateReducer,
    format_execution_error,
)
from backend.engine.runtime.registry_base import BaseModuleRegistry
from modules.common.base_module import ModuleExecutionError

from .batch_runner import WorkflowBatchRunner
from .models import (
    RunNodeState,
    WorkflowDocument,
    WorkflowEdge,
    WorkflowExecutionRequest,
    WorkflowGraph,
    WorkflowNode,
    WorkflowRun,
    utc_now_iso,
)
from .node_runner import WorkflowNodeRunner

logger = logging.getLogger(__name__)


class WorkflowExecutor:
    """Runs ready DAG nodes in batches and persists every node transition."""

    def __init__(
        self,
        module_registry: BaseModuleRegistry,
        run_store: WorkflowRunRepository,
        result_cache: WorkflowResultCache,
    ) -> None:
        self.module_registry = module_registry
        self.run_store = run_store
        self.result_cache = result_cache
        self._execution_lock = RLock()
        self._cancellation_lock = Lock()
        self._active_run_ids: Set[str] = set()
        self._cancelled_run_ids: Set[str] = set()
        self._port_resolver = WorkflowPortResolver(module_registry)
        self._graph_validator = WorkflowGraphValidator(
            module_registry,
            self._port_resolver,
        )
        self._input_assembler = WorkflowInputAssembler(
            module_registry,
            self._port_resolver,
        )
        self._run_factory = WorkflowRunFactory(
            module_registry,
            self._graph_validator,
            run_store,
        )
        self._resume_planner = WorkflowResumePlanner()
        self._node_runner = WorkflowNodeRunner(
            module_registry=module_registry,
            run_store=run_store,
            result_cache=result_cache,
            input_assembler=self._input_assembler,
            cancellation_probe=self._raise_if_cancelled,
        )
        self._batch_runner = WorkflowBatchRunner(
            module_registry=module_registry,
            run_store=run_store,
            input_assembler=self._input_assembler,
            node_runner=self._node_runner,
            execution_lock=self._execution_lock,
            persist_cancellation=self._persist_cancelled_run,
        )

    def validate_graph(self, graph: WorkflowGraph) -> List[List[str]]:
        return self._graph_validator.validate(graph)

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
        return self._run_factory.create(workflow, request)

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
        with self._cancellation_lock:
            self._cancelled_run_ids.discard(run_id)
            self._active_run_ids.add(run_id)
        try:
            return await self._batch_runner.execute(run_id, node_ids)
        finally:
            with self._cancellation_lock:
                self._active_run_ids.discard(run_id)

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
        WorkflowRunStateReducer.reset_node(state)

    @staticmethod
    def _refresh_run_status(run: WorkflowRun) -> None:
        WorkflowRunStateReducer.refresh(run)

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
        return self.run_store.save(self._resume_planner.prepare(run))

    def _execute_node(
        self,
        run: WorkflowRun,
        node: WorkflowNode,
        state: RunNodeState,
        persist_progress_updates: bool = True,
    ) -> None:
        """Execute one node through the synchronous compatibility boundary."""
        self._node_runner.execute(
            run,
            node,
            state,
            persist_progress_updates,
        )

    async def _execute_node_async(
        self,
        run: WorkflowRun,
        node: WorkflowNode,
        state: RunNodeState,
        persist_progress_updates: bool = True,
    ) -> None:
        """Execute one node through its native async hook when available."""
        await self._node_runner.execute_async(
            run,
            node,
            state,
            persist_progress_updates,
        )

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
        return self._input_assembler.should_execute(run, node)

    @staticmethod
    def _edge_is_active(run: WorkflowRun, edge: WorkflowEdge) -> bool:
        return WorkflowInputAssembler.edge_is_active(run, edge)

    def _assemble_input(self, run: WorkflowRun, node: WorkflowNode) -> Any:
        return self._input_assembler.assemble(run, node)

    def _resolve_ports(
        self,
        edge: WorkflowEdge,
        node_by_id: Mapping[str, WorkflowNode],
    ) -> Tuple[str, str]:
        return self._port_resolver.resolve(edge, node_by_id)

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
        return format_execution_error(error, include_type=include_type)
