"""Execute one workflow node with shared cache, progress, and usage semantics."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from backend.core.telemetry import trace_node_execution
from backend.domains.workflow.application import (
    WorkflowInputAssembler,
    WorkflowResultCache,
    WorkflowRunRepository,
)
from backend.domains.workflow.domain import DagExecutionError
from backend.engine.runtime.registry_base import BaseModuleRegistry
from backend.providers.openai_pricing import calculate_openai_cost
from modules.common.base_module import BaseModule

from .history import compact_history_value
from .models import RunNodeState, WorkflowNode, WorkflowRun, utc_now_iso

CancellationProbe = Callable[[str], None]


@dataclass(slots=True)
class PreparedNodeExecution:
    input_payload: Any
    module: BaseModule
    validated_config: dict[str, Any]
    cache_key: str
    cache_enabled: bool
    output: Any
    started_at: float
    progress_callback: Callable[[dict[str, Any]], None]


class WorkflowNodeRunner:
    """Own the lifecycle that is identical for sync and async node execution."""

    def __init__(
        self,
        *,
        module_registry: BaseModuleRegistry,
        run_store: WorkflowRunRepository,
        result_cache: WorkflowResultCache,
        input_assembler: WorkflowInputAssembler,
        cancellation_probe: CancellationProbe,
    ) -> None:
        self._module_registry = module_registry
        self._run_store = run_store
        self._result_cache = result_cache
        self._input_assembler = input_assembler
        self._cancellation_probe = cancellation_probe

    def execute(
        self,
        run: WorkflowRun,
        node: WorkflowNode,
        state: RunNodeState,
        persist_progress_updates: bool = True,
    ) -> None:
        prepared = self._prepare(run, node, state, persist_progress_updates)
        output = prepared.output
        if output is None:
            self._cancellation_probe(run.id)
            with trace_node_execution(
                run.workflow_id,
                run.id,
                node.id,
                node.module_type,
                state.batch_index,
            ):
                prepared.module.set_progress_callback(prepared.progress_callback)
                try:
                    output = self._module_registry.execute(
                        node.module_type,
                        prepared.input_payload,
                        prepared.validated_config,
                    )
                finally:
                    prepared.module.set_progress_callback(None)
            self._cancellation_probe(run.id)
            if prepared.cache_enabled:
                self._result_cache.put(prepared.cache_key, output)
        self._complete(node, state, prepared, output)

    async def execute_async(
        self,
        run: WorkflowRun,
        node: WorkflowNode,
        state: RunNodeState,
        persist_progress_updates: bool = True,
    ) -> None:
        prepared = await asyncio.to_thread(
            self._prepare,
            run,
            node,
            state,
            persist_progress_updates,
        )
        output = prepared.output
        if output is None:
            await asyncio.to_thread(self._cancellation_probe, run.id)
            with trace_node_execution(
                run.workflow_id,
                run.id,
                node.id,
                node.module_type,
                state.batch_index,
            ):
                prepared.module.set_progress_callback(prepared.progress_callback)
                try:
                    output = await self._module_registry.execute_async(
                        node.module_type,
                        prepared.input_payload,
                        prepared.validated_config,
                    )
                finally:
                    prepared.module.set_progress_callback(None)
            await asyncio.to_thread(self._cancellation_probe, run.id)
            if prepared.cache_enabled:
                await asyncio.to_thread(
                    self._result_cache.put,
                    prepared.cache_key,
                    output,
                )
        self._complete(node, state, prepared, output)

    def _prepare(
        self,
        run: WorkflowRun,
        node: WorkflowNode,
        state: RunNodeState,
        persist_progress_updates: bool,
    ) -> PreparedNodeExecution:
        input_payload = self._input_assembler.assemble(run, node)
        module = self._module_registry.get(node.module_type)
        validated_config = module.validate_config(node.config).model_dump(mode="json")
        cache_payload = {
            "input": module.input_model.model_validate(input_payload).model_dump(mode="json"),
            "config": validated_config,
        }
        cache_key = self._result_cache.key(
            f"{node.module_type}@{module.definition.version}", cache_payload
        )
        started_at = time.perf_counter()
        self._start_state(state, input_payload, validated_config, cache_key)
        if persist_progress_updates:
            self._run_store.save_progress(run, node.id)

        progress_callback = self._progress_callback(
            run,
            node,
            state,
            persist_progress_updates=persist_progress_updates,
        )
        cache_enabled = self._cache_enabled(run, node, module)
        output = self._result_cache.get(cache_key) if cache_enabled else None
        state.cache_hit = output is not None
        return PreparedNodeExecution(
            input_payload=input_payload,
            module=module,
            validated_config=validated_config,
            cache_key=cache_key,
            cache_enabled=cache_enabled,
            output=output,
            started_at=started_at,
            progress_callback=progress_callback,
        )

    @staticmethod
    def _start_state(
        state: RunNodeState,
        input_payload: Any,
        validated_config: dict[str, Any],
        cache_key: str,
    ) -> None:
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

    def _progress_callback(
        self,
        run: WorkflowRun,
        node: WorkflowNode,
        state: RunNodeState,
        *,
        persist_progress_updates: bool,
    ) -> Callable[[dict[str, Any]], None]:
        last_persisted_at = 0.0
        last_phase: Any = None

        def persist_progress(progress: dict[str, Any]) -> None:
            nonlocal last_persisted_at, last_phase
            self._cancellation_probe(run.id)
            compact_progress = compact_history_value(progress)
            state.progress = compact_progress
            now = time.monotonic()
            phase = compact_progress.get("phase")
            is_final = self._progress_is_final(compact_progress)
            should_persist = (
                last_persisted_at == 0.0
                or phase != last_phase
                or is_final
                or now - last_persisted_at >= 1.0
            )
            if should_persist and persist_progress_updates:
                self._run_store.save_progress(run, node.id)
                last_persisted_at = now
                last_phase = phase

        return persist_progress

    @staticmethod
    def _progress_is_final(progress: dict[str, Any]) -> bool:
        completed_total_pairs = (
            ("completed_batches", "total_batches"),
            ("completed_items", "total_items"),
            ("completed_sheets", "total_sheets"),
            ("completed_tables", "total_tables"),
        )
        return any(
            isinstance(progress.get(completed_key), (int, float))
            and isinstance(progress.get(total_key), (int, float))
            and progress[total_key] > 0
            and progress[completed_key] >= progress[total_key]
            for completed_key, total_key in completed_total_pairs
        )

    @staticmethod
    def _cache_enabled(
        run: WorkflowRun,
        node: WorkflowNode,
        module: BaseModule,
    ) -> bool:
        return (
            run.use_cache
            and module.definition.cacheable
            and (
                run.cache_only_module_types is None
                or node.module_type in run.cache_only_module_types
            )
        )

    def _complete(
        self,
        node: WorkflowNode,
        state: RunNodeState,
        prepared: PreparedNodeExecution,
        output: Any,
    ) -> None:
        self._validate_output(node, prepared.module, output)
        state.output = output
        state.status = "succeeded"
        state.outcome = prepared.module.execution_outcome(output, state.cache_hit)
        state.completed_at = utc_now_iso()
        state.elapsed_ms = round((time.perf_counter() - prepared.started_at) * 1000, 2)

        node_cost, node_usage = self._output_usage(output, prepared.validated_config)
        if node_usage is None and not state.cache_hit:
            module_cost, module_usage = self._module_usage(
                prepared.module,
                prepared.validated_config,
            )
            if module_usage is not None:
                node_usage = module_usage
                node_cost = module_cost if module_cost is not None else node_cost
        state.cost_usd = node_cost
        state.usage = node_usage

    @staticmethod
    def _validate_output(node: WorkflowNode, module: BaseModule, output: Any) -> None:
        branch_ports = set(module.definition.branch_outputs.values())
        if module.definition.raw_output:
            missing_outputs: list[str] = []
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

    @classmethod
    def _output_usage(
        cls,
        output: Any,
        config: Mapping[str, Any],
    ) -> tuple[float | None, dict[str, int] | None]:
        if not isinstance(output, Mapping):
            return None, None
        answer = output.get("answer_json")
        if isinstance(answer, Mapping):
            return (
                answer.get("estimated_cost_usd"),
                cls._usage_mapping(answer.get("api_usage")),
            )
        semantic = output.get("semantic_match")
        if isinstance(semantic, Mapping):
            metrics = semantic.get("metrics") or {}
            if not isinstance(metrics, Mapping):
                return None, None
            return (
                metrics.get("estimated_cost_usd"),
                cls._usage_mapping(metrics.get("api_usage") or {}),
            )
        metrics = output.get("metrics")
        if isinstance(metrics, Mapping):
            return cls._metric_usage(metrics)
        if "usage" in output or "_usage" in output:
            usage = output.get("usage") or output.get("_usage")
            model = output.get("model") or config.get("model") or ""
            return cls._priced_usage(usage, str(model))
        return None, None

    @staticmethod
    def _usage_mapping(raw_usage: Any) -> dict[str, int] | None:
        if not isinstance(raw_usage, Mapping):
            return None
        return {
            str(key): int(value)
            for key, value in raw_usage.items()
            if value is not None
        }

    @classmethod
    def _metric_usage(
        cls,
        metrics: Mapping[str, Any],
    ) -> tuple[float | None, dict[str, int] | None]:
        cost = metrics.get("estimated_cost_usd")
        raw_usage = metrics.get("api_usage") or {}
        if isinstance(raw_usage, Mapping) and raw_usage:
            return cost, cls._usage_mapping(raw_usage)
        if metrics.get("total_tokens") is None:
            return cost, None
        total_tokens = int(metrics.get("total_tokens") or 0)
        return cost, {
            "prompt_tokens": total_tokens,
            "completion_tokens": 0,
            "cached_tokens": 0,
            "total_tokens": total_tokens,
        }

    @classmethod
    def _module_usage(
        cls,
        module: BaseModule,
        config: Mapping[str, Any],
    ) -> tuple[float | None, dict[str, int] | None]:
        raw_usage = getattr(module, "last_usage", None)
        if not isinstance(raw_usage, Mapping):
            return None, None
        model = getattr(module, "last_model", "") or config.get("model") or ""
        return cls._priced_usage(raw_usage, str(model), price_only_when_used=True)

    @staticmethod
    def _priced_usage(
        raw_usage: Any,
        model: str,
        *,
        price_only_when_used: bool = False,
    ) -> tuple[float | None, dict[str, int] | None]:
        if not isinstance(raw_usage, Mapping):
            return None, None
        usage = {
            "prompt_tokens": int(raw_usage.get("prompt_tokens", 0) or 0),
            "completion_tokens": int(raw_usage.get("completion_tokens", 0) or 0),
            "cached_tokens": int(raw_usage.get("cached_tokens", 0) or 0),
            "total_tokens": int(raw_usage.get("total_tokens", 0) or 0),
        }
        if price_only_when_used and usage["total_tokens"] <= 0:
            return None, usage
        cost = calculate_openai_cost(
            model_name=model,
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            cached_tokens=usage["cached_tokens"],
        )
        return cost, usage


__all__ = ["PreparedNodeExecution", "WorkflowNodeRunner"]
