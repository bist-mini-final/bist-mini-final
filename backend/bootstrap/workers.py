"""Explicit registry that composes one-shot domain worker processes."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from importlib import import_module
from types import MappingProxyType
from typing import cast

WorkerMain = Callable[..., int]

WORKER_TARGETS = MappingProxyType(
    {
        "workflow": "backend.engine.worker.main:main",
        "ingestion-embedding": (
            "backend.storage.data_sources.embedding_shard_worker_main:main"
        ),
        "ingestion-vector": (
            "backend.storage.data_sources.vector_shard_worker_main:main"
        ),
        "bi-materialization": "backend.features.bi.materialization_worker_main:main",
        "bi-question": "backend.features.bi.question_worker_main:main",
        "benchmark": "backend.features.benchmark.worker_main:main",
    }
)


def registered_worker_kinds() -> tuple[str, ...]:
    """Return stable worker kinds accepted by the process entrypoint."""

    return tuple(WORKER_TARGETS)


def _load_worker(kind: str) -> WorkerMain:
    try:
        target = WORKER_TARGETS[kind]
    except KeyError as error:
        supported = ", ".join(registered_worker_kinds())
        raise ValueError(f"지원하지 않는 worker kind입니다: {kind} ({supported})") from error
    module_name, function_name = target.split(":", 1)
    function = getattr(import_module(module_name), function_name)
    if not callable(function):
        raise TypeError(f"worker entrypoint가 callable이 아닙니다: {target}")
    return cast(WorkerMain, function)


def run_worker(kind: str, argv: Sequence[str] = ()) -> int:
    """Build and run one registered worker without leaking targets to deploy specs."""

    worker = _load_worker(kind)
    if kind == "workflow":
        return worker(tuple(argv))
    if argv:
        raise ValueError(f"{kind} worker는 추가 인자를 지원하지 않습니다: {list(argv)}")
    return worker()


__all__ = ["WORKER_TARGETS", "registered_worker_kinds", "run_worker"]
