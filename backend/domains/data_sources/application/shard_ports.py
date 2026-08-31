"""Ports used by distributed ingestion coordination."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any, Mapping, Protocol, Sequence

from backend.domains.data_sources.domain import (
    IngestionShard,
    IngestionShardPhase,
    IngestionShardPhaseSnapshot,
)


class IngestionShardRepository(Protocol):
    def prepare_phase(
        self,
        operation_id: str,
        phase: IngestionShardPhase,
        payloads: Sequence[Mapping[str, Any]],
    ) -> None: ...

    def phase_snapshot(
        self,
        operation_id: str,
        phase: IngestionShardPhase,
    ) -> IngestionShardPhaseSnapshot: ...

    def requeue_shards(
        self,
        operation_id: str,
        phase: IngestionShardPhase,
        shard_indexes: Sequence[int],
    ) -> int: ...

    def operation_lock(
        self,
        operation_id: str,
        purpose: str,
    ) -> AbstractContextManager[None]: ...


class IngestionShardArtifacts(Protocol):
    def put_manifest(
        self,
        artifact_id: str,
        shard_index: int,
        items: Sequence[Mapping[str, Any]],
    ) -> Any: ...

    def vector_shard_is_valid(
        self,
        artifact_id: str,
        shard_index: int,
        count: int,
        dimension: int,
    ) -> bool: ...

    def assemble_embedding_artifact(
        self,
        artifact_id: str,
        shard_counts: Sequence[int],
        dimension: int,
    ) -> Any: ...

    def clear_operation_shards(self, artifact_id: str) -> int: ...


class VectorReplacePlanPort(Protocol):
    @property
    def index_id(self) -> str: ...

    @property
    def operation_id(self) -> str: ...

    @property
    def staging_name(self) -> str: ...

    @property
    def staging_uuid(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    @property
    def metadata(self) -> dict[str, Any]: ...

    @property
    def published(self) -> bool: ...


class DistributedVectorStore(Protocol):
    def collection_document_count(self, collection_uuid: str) -> int: ...

    def publish_prepared_collection(self, plan: Any) -> None: ...


class IngestionShardWorkerRepository(Protocol):
    def claim_next(
        self,
        phase: IngestionShardPhase,
        worker_id: str,
    ) -> IngestionShard | None: ...

    def heartbeat(self, shard: IngestionShard) -> bool: ...

    def complete(
        self,
        shard: IngestionShard,
        *,
        total_tokens: int | None = None,
        duration_seconds: float,
    ) -> None: ...

    def fail(self, shard: IngestionShard, error_message: str) -> None: ...


class EmbeddingShardExecutor(Protocol):
    def execute(self, payload: dict[str, Any]) -> int: ...


class VectorShardExecutor(Protocol):
    def execute(self, payload: dict[str, Any]) -> None: ...


__all__ = [
    "DistributedVectorStore",
    "EmbeddingShardExecutor",
    "IngestionShardArtifacts",
    "IngestionShardRepository",
    "IngestionShardWorkerRepository",
    "VectorShardExecutor",
    "VectorReplacePlanPort",
]
