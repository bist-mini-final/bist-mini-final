"""Explicit registry that composes one-shot domain worker processes."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Sequence
from importlib import import_module
from types import MappingProxyType
from typing import cast

from backend.bootstrap.application import RuntimeContainer
from backend.core.settings import KUBERNETES_WORKFLOW_QUEUE
from backend.domains.data_sources.infrastructure import (
    OpenAIEmbeddingShardExecutor,
    PgVectorCopyShardExecutor,
)
from backend.domains.data_sources.infrastructure.filesystem import (
    IngestionShardArtifactStore,
)
from backend.domains.data_sources.infrastructure.postgres import (
    PostgresIngestionShardRepository,
)

WorkerMain = Callable[..., int]

WORKER_TARGETS = MappingProxyType(
    {
        "workflow": "backend.domains.workflow.workers.main:main",
        "ingestion-embedding": (
            "backend.domains.data_sources.workers.embedding:main"
        ),
        "ingestion-vector": (
            "backend.domains.data_sources.workers.vector:main"
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
        runtime = RuntimeContainer.create(
            initialize_schema=False,
            require_database=True,
        )
        try:
            return worker(
                tuple(argv),
                services=runtime.services,
                default_queue=KUBERNETES_WORKFLOW_QUEUE,
            )
        finally:
            runtime.close()
    if kind in {"ingestion-embedding", "ingestion-vector"}:
        logging.basicConfig(
            level=getattr(
                logging,
                os.getenv("LOG_LEVEL", "INFO").upper(),
                logging.INFO,
            ),
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        runtime = RuntimeContainer.create(
            initialize_schema=False,
            require_database=True,
        )
        try:
            embedding_store = runtime.services.module_registry.embedding_artifact_store
            artifacts = IngestionShardArtifactStore(embedding_store)
            repository = PostgresIngestionShardRepository(
                runtime.services.db_manager.database_url
            )
            executor = (
                OpenAIEmbeddingShardExecutor(artifacts, runtime.embedding_encoder)
                if kind == "ingestion-embedding"
                else PgVectorCopyShardExecutor(
                    artifacts,
                    embedding_store,
                    runtime.services.pgvector_store,
                )
            )
            return worker(repository=repository, executor=executor)
        finally:
            runtime.close()
    if argv:
        raise ValueError(f"{kind} worker는 추가 인자를 지원하지 않습니다: {list(argv)}")
    return worker()


__all__ = ["WORKER_TARGETS", "registered_worker_kinds", "run_worker"]
