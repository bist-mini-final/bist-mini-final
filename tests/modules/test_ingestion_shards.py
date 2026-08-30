from __future__ import annotations

import struct
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from backend.storage.data_sources.ingestion_shards import (
    IngestionShard,
    IngestionShardPhaseSnapshot,
)
from backend.storage.data_sources.shard_artifacts import IngestionShardArtifactStore
from backend.storage.data_sources.shard_coordinator import IngestionShardCoordinator
from backend.storage.embedding_artifacts import EmbeddingArtifactStore


class ImmediateEmbeddingRepository:
    def __init__(self, artifacts: IngestionShardArtifactStore) -> None:
        self.artifacts = artifacts
        self.shards: tuple[IngestionShard, ...] = ()

    def prepare_phase(
        self,
        operation_id: str,
        phase: str,
        payloads: list[dict[str, Any]],
    ) -> None:
        assert phase == "embedding"
        completed: list[IngestionShard] = []
        for shard_index, payload in enumerate(payloads):
            count = int(payload["count"])
            self.artifacts.put_vector_shard(
                operation_id,
                shard_index,
                [[float(payload["start"] + offset), 0.5] for offset in range(count)],
                dimension=2,
            )
            completed.append(
                IngestionShard(
                    operation_id=operation_id,
                    phase="embedding",
                    shard_index=shard_index,
                    status="succeeded",
                    payload=payload,
                    attempt_count=1,
                    total_tokens=count * 3,
                    duration_seconds=0.2,
                )
            )
        self.shards = tuple(completed)

    def phase_snapshot(self, _operation_id: str, _phase: str) -> IngestionShardPhaseSnapshot:
        return IngestionShardPhaseSnapshot(self.shards)

    def requeue_shards(
        self,
        _operation_id: str,
        _phase: str,
        shard_indexes: list[int],
    ) -> int:
        assert not shard_indexes
        return 0

    @contextmanager
    def operation_lock(self, _operation_id: str, _purpose: str):
        yield


def test_embedding_shards_are_joined_in_global_order(tmp_path: Path) -> None:
    embedding_store = EmbeddingArtifactStore(tmp_path)
    artifacts = IngestionShardArtifactStore(embedding_store)
    repository = ImmediateEmbeddingRepository(artifacts)
    coordinator = IngestionShardCoordinator(
        repository,  # type: ignore[arg-type]
        artifacts,
        enabled=True,
        poll_seconds=0.001,
        wait_timeout_seconds=1,
    )
    progress: list[dict[str, Any]] = []
    artifact_id = "a" * 64

    result = coordinator.embed(
        artifact_id=artifact_id,
        items=[{"text": f"cell {index}"} for index in range(5)],
        model_name="custom-2d",
        dimension=2,
        batch_size=2,
        progress_callback=progress.append,
    )

    assert result.shard_count == 3
    assert result.total_tokens == 15
    assert result.worker_seconds == 0.6
    assert embedding_store.is_valid(artifact_id, 5, 2)
    raw = b"".join(embedding_store.iter_raw_batches(artifact_id, 5, 2, 5))
    assert struct.unpack("<10f", raw) == (
        0.0,
        0.5,
        1.0,
        0.5,
        2.0,
        0.5,
        3.0,
        0.5,
        4.0,
        0.5,
    )
    assert progress[-1]["execution_mode"] == "kubernetes_shards"
    assert progress[-1]["completed_batches"] == 3


def test_vector_range_view_streams_only_requested_rows(tmp_path: Path) -> None:
    store = EmbeddingArtifactStore(tmp_path)
    artifact_id = "b" * 64
    store.put(
        artifact_id,
        [[0.0, 0.1], [1.0, 1.1], [2.0, 2.1], [3.0, 3.1]],
    )

    view = store.vector_range_sequence(artifact_id, 1, 3, 4, 2)
    batches = list(view.iter_raw_batches(1))

    assert len(view) == 2
    assert [struct.unpack("<2f", batch) for batch in batches] == pytest.approx([
        (1.0, 1.100000023841858),
        (2.0, 2.0999999046325684),
    ])
