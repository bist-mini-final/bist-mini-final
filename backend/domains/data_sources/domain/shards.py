"""Distributed ingestion shard states and lease failures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

IngestionShardPhase = Literal["embedding", "vector_copy"]
IngestionShardStatus = Literal["queued", "running", "succeeded", "failed"]


class IngestionShard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str = Field(min_length=1, max_length=128)
    phase: IngestionShardPhase
    shard_index: int = Field(ge=0)
    status: IngestionShardStatus
    payload: dict[str, Any]
    worker_id: str | None = None
    lease_token: str | None = None
    attempt_count: int = Field(ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    duration_seconds: float | None = Field(default=None, ge=0)
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class IngestionShardPhaseSnapshot:
    shards: tuple[IngestionShard, ...]

    @property
    def total(self) -> int:
        return len(self.shards)

    @property
    def completed(self) -> int:
        return sum(shard.status == "succeeded" for shard in self.shards)

    @property
    def failed(self) -> tuple[IngestionShard, ...]:
        return tuple(shard for shard in self.shards if shard.status == "failed")

    @property
    def total_tokens(self) -> int:
        return sum(shard.total_tokens or 0 for shard in self.shards)

    @property
    def worker_seconds(self) -> float:
        return round(sum(shard.duration_seconds or 0 for shard in self.shards), 3)

    @property
    def terminal(self) -> bool:
        return bool(self.shards) and all(
            shard.status in {"succeeded", "failed"} for shard in self.shards
        )


class IngestionShardLeaseLost(RuntimeError):
    """Raised when a worker finishes a shard it no longer owns."""


__all__ = [
    "IngestionShard",
    "IngestionShardLeaseLost",
    "IngestionShardPhase",
    "IngestionShardPhaseSnapshot",
    "IngestionShardStatus",
]
