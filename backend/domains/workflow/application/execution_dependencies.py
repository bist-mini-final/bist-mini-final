"""Injectable telemetry capabilities used by workflow execution."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager

TokenCostCalculator = Callable[[str, int, int, int], float]
NodeTraceFactory = Callable[[str, str, str, str, int], AbstractContextManager[object]]


def unpriced_tokens(
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int = 0,
    cached_tokens: int = 0,
) -> float:
    """Neutral fallback for tests and offline runtimes without a pricing adapter."""

    del model_name, prompt_tokens, completion_tokens, cached_tokens
    return 0.0


@contextmanager
def untraced_node(
    workflow_id: str,
    run_id: str,
    node_id: str,
    module_type: str,
    batch_index: int,
) -> Iterator[None]:
    """Neutral trace boundary used when telemetry is not composed."""

    del workflow_id, run_id, node_id, module_type, batch_index
    yield None


__all__ = [
    "NodeTraceFactory",
    "TokenCostCalculator",
    "unpriced_tokens",
    "untraced_node",
]
