"""Unified in-memory pipeline runner for composable module sequences and DAGs."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel

from modules.common.base_module import BaseModule
from modules.common.exceptions import ModuleExecutionError, PipelineBaseError

logger = logging.getLogger(__name__)


@dataclass
class NodeExecutionRecord:
    """Execution telemetry and result for a single module in a pipeline run."""

    module_type: str
    input_data: Any
    output_data: Any
    elapsed_ms: float
    usage: Optional[Dict[str, int]] = None
    cost_usd: Optional[float] = None
    status: str = "succeeded"
    error: Optional[str] = None


@dataclass
class PipelineExecutionResult:
    """Aggregated result of executing a composable pipeline."""

    final_output: Any
    records: List[NodeExecutionRecord] = field(default_factory=list)
    total_elapsed_ms: float = 0.0
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    status: str = "succeeded"
    error: Optional[str] = None

    def get_output(self, key: Optional[str] = None) -> Any:
        """Helper to extract a specific field or the full final output."""
        if key is None:
            return self.final_output
        if isinstance(self.final_output, dict):
            return self.final_output.get(key)
        if isinstance(self.final_output, BaseModel):
            return getattr(self.final_output, key, None)
        return None


class PipelineRunner:
    """Executes composable module sequences or DAGs in memory with zero intermediate disk I/O."""

    def __init__(self, logger_instance: Optional[logging.Logger] = None) -> None:
        self.logger = logger_instance or logger

    def run_sequence(
        self,
        modules: Sequence[BaseModule],
        initial_input: Any,
        configs: Optional[Sequence[Optional[Any]]] = None,
    ) -> PipelineExecutionResult:
        """Execute a linear sequence of modules passing the output of node N to node N+1."""
        records: List[NodeExecutionRecord] = []
        current_input = initial_input
        total_start = time.perf_counter()
        total_cost = 0.0
        total_tokens = 0

        config_list = list(configs or [None] * len(modules))

        for idx, module in enumerate(modules):
            module_type = module.definition.type
            cfg = config_list[idx] if idx < len(config_list) else None
            node_start = time.perf_counter()

            try:
                if cfg is not None:
                    output = module.run(current_input, cfg)
                else:
                    output = module.run(current_input)
                elapsed_ms = (time.perf_counter() - node_start) * 1000.0

                # Extract telemetry if present in output
                cost = 0.0
                usage = None
                if isinstance(output, dict):
                    cost = float(output.get("cost_usd", 0.0) or 0.0)
                    usage = output.get("usage")
                    if usage and isinstance(usage, dict):
                        total_tokens += sum(int(v) for v in usage.values() if isinstance(v, (int, float)))
                total_cost += cost

                record = NodeExecutionRecord(
                    module_type=module_type,
                    input_data=current_input,
                    output_data=output,
                    elapsed_ms=elapsed_ms,
                    usage=usage,
                    cost_usd=cost,
                    status="succeeded",
                )
                records.append(record)
                current_input = output

            except Exception as error:
                elapsed_ms = (time.perf_counter() - node_start) * 1000.0
                error_msg = str(error)
                self.logger.error("Pipeline sequence failed at module [%s]: %s", module_type, error_msg, exc_info=True)
                records.append(
                    NodeExecutionRecord(
                        module_type=module_type,
                        input_data=current_input,
                        output_data=None,
                        elapsed_ms=elapsed_ms,
                        status="failed",
                        error=error_msg,
                    )
                )
                total_elapsed_ms = (time.perf_counter() - total_start) * 1000.0
                return PipelineExecutionResult(
                    final_output=None,
                    records=records,
                    total_elapsed_ms=total_elapsed_ms,
                    total_cost_usd=total_cost,
                    total_tokens=total_tokens,
                    status="failed",
                    error=error_msg,
                )

        total_elapsed_ms = (time.perf_counter() - total_start) * 1000.0
        return PipelineExecutionResult(
            final_output=current_input,
            records=records,
            total_elapsed_ms=total_elapsed_ms,
            total_cost_usd=total_cost,
            total_tokens=total_tokens,
            status="succeeded",
        )


__all__ = [
    "NodeExecutionRecord",
    "PipelineExecutionResult",
    "PipelineRunner",
]
