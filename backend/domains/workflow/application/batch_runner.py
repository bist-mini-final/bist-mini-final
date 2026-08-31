"""Concurrent execution of one persisted topological workflow batch."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from typing import Any

from pydantic import ValidationError

from backend.domains.workflow.domain import (
    DagExecutionCancelled,
    DagExecutionError,
    WorkflowRunStateReducer,
    format_execution_error,
)
from backend.domains.workflow.domain.models import (
    RunNodeState,
    WorkflowNode,
    WorkflowRun,
    utc_now_iso,
)
from modules.common.base_module import ModuleExecutionError

from .input_assembly import WorkflowInputAssembler
from .module_registry import ModuleRegistryPort
from .node_runner import WorkflowNodeRunner
from .ports import WorkflowRunRepository

CancellationPersister = Callable[[str], WorkflowRun]


class WorkflowBatchRunner:
    """Prepare, concurrently execute, and atomically merge one DAG generation."""

    def __init__(
        self,
        *,
        module_registry: ModuleRegistryPort,
        run_store: WorkflowRunRepository,
        input_assembler: WorkflowInputAssembler,
        node_runner: WorkflowNodeRunner,
        execution_lock: Any,
        persist_cancellation: CancellationPersister,
    ) -> None:
        self._module_registry = module_registry
        self._run_store = run_store
        self._input_assembler = input_assembler
        self._node_runner = node_runner
        self._execution_lock = execution_lock
        self._persist_cancellation = persist_cancellation

    async def execute(
        self,
        run_id: str,
        node_ids: tuple[str, ...],
    ) -> WorkflowRun:
        self._validate_request(node_ids)
        base_run, selected_nodes = await asyncio.to_thread(
            self._prepare,
            run_id,
            node_ids,
        )
        results, errors = await self._execute_isolated_batch(
            run_id,
            base_run,
            selected_nodes,
        )
        merged = await asyncio.to_thread(
            self._merge,
            run_id,
            node_ids,
            results,
        )
        await self._raise_errors(run_id, errors)
        return merged

    @staticmethod
    def _validate_request(node_ids: tuple[str, ...]) -> None:
        if not node_ids:
            raise DagExecutionError("실행할 batch 노드가 없습니다")
        if len(set(node_ids)) != len(node_ids):
            raise DagExecutionError("batch에 중복 노드 ID가 있습니다")

    async def _execute_isolated_batch(
        self,
        run_id: str,
        base_run: WorkflowRun,
        selected_nodes: tuple[WorkflowNode, ...],
    ) -> tuple[dict[str, RunNodeState], dict[str, Exception]]:
        module_locks: dict[str, asyncio.Lock] = {}
        tasks: dict[str, asyncio.Task[tuple[RunNodeState, Exception | None]]] = {}
        async with asyncio.TaskGroup() as task_group:
            for node in selected_nodes:
                module_lock = module_locks.setdefault(node.module_type, asyncio.Lock())
                tasks[node.id] = task_group.create_task(
                    self._execute_isolated_node(base_run, node, module_lock),
                    name=f"workflow:{run_id}:{node.id}",
                )
        outcomes = {node_id: task.result() for node_id, task in tasks.items()}
        return (
            {node_id: outcome[0] for node_id, outcome in outcomes.items()},
            {
                node_id: error
                for node_id, (_, error) in outcomes.items()
                if error is not None
            },
        )

    async def _execute_isolated_node(
        self,
        base_run: WorkflowRun,
        node: WorkflowNode,
        module_lock: asyncio.Lock,
    ) -> tuple[RunNodeState, Exception | None]:
        snapshot = base_run.model_copy(deep=True)
        state = snapshot.nodes[node.id]
        if state.status in ("succeeded", "skipped"):
            return state, None
        if state.status in ("failed", "running"):
            WorkflowRunStateReducer.reset_node(state)
        should_execute, skip_reason = self._input_assembler.should_execute(snapshot, node)
        if not should_execute:
            state.status = "skipped"
            state.outcome = None
            state.skip_reason = skip_reason
            state.completed_at = utc_now_iso()
            return state, None

        module = self._module_registry.get(node.module_type)
        policy = module.definition.task or module.definition.task_policy
        for attempt in range(policy.retries + 1):
            try:
                async with module_lock:
                    await self._node_runner.execute_async(snapshot, node, state, False)
                return state, None
            except DagExecutionCancelled as error:
                return state, error
            except Exception as error:
                if attempt >= policy.retries:
                    self._mark_failed(state, error)
                    return state, error
                WorkflowRunStateReducer.reset_node(state)
                if policy.retry_delay_seconds:
                    await asyncio.sleep(policy.retry_delay_seconds)
        return state, None

    @staticmethod
    def _mark_failed(state: RunNodeState, error: Exception) -> None:
        state.status = "failed"
        state.outcome = "failed"
        state.error = format_execution_error(
            error,
            include_type=not isinstance(
                error,
                (DagExecutionError, ValidationError, ModuleExecutionError),
            ),
        )
        state.completed_at = utc_now_iso()

    async def _raise_errors(
        self,
        run_id: str,
        errors: Mapping[str, Exception],
    ) -> None:
        cancellation = next(
            (error for error in errors.values() if isinstance(error, DagExecutionCancelled)),
            None,
        )
        if cancellation is not None:
            await asyncio.to_thread(self._persist_cancellation, run_id)
            raise DagExecutionCancelled(
                "실행이 사용자 요청으로 중단되었습니다"
            ) from cancellation
        if errors:
            failed_nodes = ", ".join(sorted(errors))
            first_error = errors[sorted(errors)[0]]
            raise DagExecutionError(f"batch 노드 실행 실패: {failed_nodes}") from first_error

    def _prepare(
        self,
        run_id: str,
        node_ids: tuple[str, ...],
    ) -> tuple[WorkflowRun, tuple[WorkflowNode, ...]]:
        with self._execution_lock:
            run = self._run_store.load(run_id)
            selected_nodes = self._select_persisted_batch(run, node_ids)
            batch = run.batches[run.nodes[selected_nodes[0].id].batch_index]
            run.status = "running"
            batch.status = "running"
            batch.started_at = batch.started_at or utc_now_iso()
            batch.completed_at = None
            self._start_nodes(run, selected_nodes)
            WorkflowRunStateReducer.refresh(run)
            self._persist_start(run, selected_nodes)
            return run, selected_nodes

    @staticmethod
    def _select_persisted_batch(
        run: WorkflowRun,
        node_ids: tuple[str, ...],
    ) -> tuple[WorkflowNode, ...]:
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
        return selected_nodes

    def _start_nodes(
        self,
        run: WorkflowRun,
        selected_nodes: tuple[WorkflowNode, ...],
    ) -> None:
        started_at = utc_now_iso()
        for node in selected_nodes:
            state = run.nodes[node.id]
            if state.status in ("succeeded", "skipped"):
                continue
            if state.status in ("failed", "running"):
                WorkflowRunStateReducer.reset_node(state)
            should_execute, skip_reason = self._input_assembler.should_execute(run, node)
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

    def _persist_start(
        self,
        run: WorkflowRun,
        selected_nodes: tuple[WorkflowNode, ...],
    ) -> None:
        for node in selected_nodes:
            state = run.nodes[node.id]
            if state.status == "running":
                self._run_store.save_progress(run, node.id)
            elif state.status == "skipped":
                self._run_store.save_node(run, node.id)

    def _merge(
        self,
        run_id: str,
        node_ids: tuple[str, ...],
        results: Mapping[str, RunNodeState],
    ) -> WorkflowRun:
        with self._execution_lock:
            merged = self._run_store.load(run_id)
            for node_id in node_ids:
                merged.nodes[node_id] = results[node_id]
            WorkflowRunStateReducer.refresh(merged)
            for node_id in node_ids:
                self._run_store.save_node(merged, node_id)
            return merged


__all__ = ["WorkflowBatchRunner"]
