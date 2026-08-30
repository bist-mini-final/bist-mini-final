"""Parent-side orchestration for distributed Excel ingestion shard Jobs."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from backend.core.settings import (
    INGESTION_SHARD_POLL_SECONDS,
    INGESTION_SHARD_WAIT_TIMEOUT_SECONDS,
)
from backend.storage.pgvector_store import PgVectorReplacePlan, PgVectorStore
from modules.common.exceptions import ModuleExecutionError

from .ingestion_shards import (
    IngestionShardPhase,
    IngestionShardPhaseSnapshot,
    PostgresIngestionShardRepository,
)
from .shard_artifacts import IngestionShardArtifactStore

ProgressCallback = Callable[[dict[str, Any]], None]


@dataclass(frozen=True, slots=True)
class DistributedEmbeddingResult:
    """Usage and elapsed-time aggregate returned to CellTextEmbedder."""

    duration_seconds: float
    worker_seconds: float
    total_tokens: int
    shard_count: int


@dataclass(frozen=True, slots=True)
class DistributedVectorCopyResult:
    duration_seconds: float
    worker_seconds: float
    shard_count: int


class IngestionShardCoordinator:
    """Create child work, wait on a durable barrier, and assemble artifacts."""

    def __init__(
        self,
        repository: PostgresIngestionShardRepository,
        artifacts: IngestionShardArtifactStore,
        *,
        enabled: bool,
        pgvector_store: PgVectorStore | None = None,
        poll_seconds: float = INGESTION_SHARD_POLL_SECONDS,
        wait_timeout_seconds: int = INGESTION_SHARD_WAIT_TIMEOUT_SECONDS,
    ) -> None:
        self.repository = repository
        self.artifacts = artifacts
        self.enabled = enabled
        self.pgvector_store = pgvector_store
        self.poll_seconds = poll_seconds
        self.wait_timeout_seconds = wait_timeout_seconds

    @staticmethod
    def _ranges(total_items: int, shard_size: int) -> tuple[tuple[int, int], ...]:
        if total_items <= 0:
            raise ModuleExecutionError("분산 ingestion 대상 문서가 없습니다")
        if shard_size <= 0:
            raise ModuleExecutionError("분산 ingestion shard 크기는 양수여야 합니다")
        return tuple(
            (start, min(start + shard_size, total_items))
            for start in range(0, total_items, shard_size)
        )

    def embed(
        self,
        *,
        artifact_id: str,
        items: Sequence[Mapping[str, Any]],
        model_name: str,
        dimension: int,
        batch_size: int,
        progress_callback: ProgressCallback | None = None,
    ) -> DistributedEmbeddingResult:
        """Fan embedding API batches out to KEDA Jobs and join their part files."""

        if not self.enabled:
            raise ModuleExecutionError("분산 ingestion shard 실행이 활성화되지 않았습니다")
        ranges = self._ranges(len(items), batch_size)
        payloads: list[dict[str, Any]] = []
        shard_counts: list[int] = []
        for shard_index, (start, stop) in enumerate(ranges):
            shard_items = items[start:stop]
            self.artifacts.put_manifest(artifact_id, shard_index, shard_items)
            count = stop - start
            shard_counts.append(count)
            payloads.append(
                {
                    "artifact_id": artifact_id,
                    "model": model_name,
                    "dimension": dimension,
                    "batch_size": batch_size,
                    "start": start,
                    "stop": stop,
                    "count": count,
                }
            )

        self.repository.prepare_phase(artifact_id, "embedding", payloads)
        initial = self.repository.phase_snapshot(artifact_id, "embedding")
        missing = [
            shard.shard_index
            for shard in initial.shards
            if shard.status == "succeeded"
            and not self.artifacts.vector_shard_is_valid(
                artifact_id,
                shard.shard_index,
                int(shard.payload["count"]),
                dimension,
            )
        ]
        self.repository.requeue_shards(artifact_id, "embedding", missing)

        started = time.perf_counter()
        snapshot = self._wait_for_phase(
            artifact_id,
            "embedding",
            total_items=len(items),
            progress_phase="embedding_batches",
            progress_callback=progress_callback,
        )
        if progress_callback is not None:
            progress_callback(
                {
                    "phase": "embedding_assembly",
                    "execution_mode": "kubernetes_shards",
                    "completed_batches": snapshot.total,
                    "total_batches": snapshot.total,
                    "completed_items": len(items),
                    "total_items": len(items),
                    "running_jobs": 0,
                    "queued_jobs": 0,
                }
            )
        with self.repository.operation_lock(artifact_id, "artifact"):
            self.artifacts.assemble_embedding_artifact(
                artifact_id,
                shard_counts,
                dimension,
            )
        return DistributedEmbeddingResult(
            duration_seconds=round(time.perf_counter() - started, 3),
            worker_seconds=snapshot.worker_seconds,
            total_tokens=snapshot.total_tokens,
            shard_count=snapshot.total,
        )

    def copy_vectors(
        self,
        *,
        plan: PgVectorReplacePlan,
        artifact_id: str,
        items: Sequence[Mapping[str, Any]],
        shard_size: int,
        progress_callback: ProgressCallback | None = None,
    ) -> DistributedVectorCopyResult:
        """Fan deterministic COPY ranges out and publish after a durable barrier."""

        if not self.enabled or self.pgvector_store is None:
            raise ModuleExecutionError("분산 pgvector shard 실행이 활성화되지 않았습니다")
        if plan.published:
            with self.repository.operation_lock(artifact_id, "artifact"):
                self.artifacts.clear_operation_shards(artifact_id)
            return DistributedVectorCopyResult(0.0, 0.0, 0)
        ranges = self._ranges(len(items), shard_size)
        payloads: list[dict[str, Any]] = []
        for shard_index, (start, stop) in enumerate(ranges):
            shard_items = items[start:stop]
            self.artifacts.put_manifest(artifact_id, shard_index, shard_items)
            payloads.append(
                {
                    "artifact_id": artifact_id,
                    "index_id": plan.index_id,
                    "operation_id": plan.operation_id,
                    "staging_name": plan.staging_name,
                    "staging_uuid": plan.staging_uuid,
                    "dimension": plan.dimension,
                    "metadata": plan.metadata,
                    "start": start,
                    "stop": stop,
                    "count": stop - start,
                }
            )
        self.repository.prepare_phase(plan.operation_id, "vector_copy", payloads)

        started = time.perf_counter()
        snapshot = self._wait_for_phase(
            plan.operation_id,
            "vector_copy",
            total_items=len(items),
            progress_phase="storage_batches",
            progress_callback=progress_callback,
        )
        if self.pgvector_store.collection_document_count(plan.staging_uuid) != len(items):
            # A worker may have committed COPY immediately before losing its
            # lease, or an old local volume may have lost a part. Replaying all
            # deterministic ranges is safe and repairs either case.
            self.repository.requeue_shards(
                plan.operation_id,
                "vector_copy",
                [shard.shard_index for shard in snapshot.shards],
            )
            snapshot = self._wait_for_phase(
                plan.operation_id,
                "vector_copy",
                total_items=len(items),
                progress_phase="storage_batches",
                progress_callback=progress_callback,
            )
        if progress_callback is not None:
            progress_callback(
                {
                    "phase": "vector_index_build",
                    "execution_mode": "kubernetes_shards",
                    "completed_batches": snapshot.total,
                    "total_batches": snapshot.total,
                    "completed_items": len(items),
                    "total_items": len(items),
                    "running_jobs": 0,
                    "queued_jobs": 0,
                }
            )
        self.pgvector_store.publish_prepared_collection(plan)
        if progress_callback is not None:
            progress_callback(
                {
                    "phase": "collection_publish",
                    "execution_mode": "kubernetes_shards",
                    "completed_batches": snapshot.total,
                    "total_batches": snapshot.total,
                    "completed_items": len(items),
                    "total_items": len(items),
                    "running_jobs": 0,
                    "queued_jobs": 0,
                }
            )
        with self.repository.operation_lock(artifact_id, "artifact"):
            self.artifacts.clear_operation_shards(artifact_id)
        return DistributedVectorCopyResult(
            duration_seconds=round(time.perf_counter() - started, 3),
            worker_seconds=snapshot.worker_seconds,
            shard_count=snapshot.total,
        )

    def _wait_for_phase(
        self,
        operation_id: str,
        phase: IngestionShardPhase,
        *,
        total_items: int,
        progress_phase: str,
        progress_callback: ProgressCallback | None,
    ) -> IngestionShardPhaseSnapshot:
        deadline = time.monotonic() + self.wait_timeout_seconds
        last_progress_signature: tuple[int, int, int] | None = None
        last_reported_at = 0.0
        while True:
            snapshot = self.repository.phase_snapshot(operation_id, phase)
            if not snapshot.shards:
                raise ModuleExecutionError(
                    f"분산 ingestion shard가 생성되지 않았습니다: {phase}"
                )
            failed = snapshot.failed
            if failed:
                first = failed[0]
                raise ModuleExecutionError(
                    "분산 ingestion shard가 최종 실패했습니다 "
                    f"({phase} {first.shard_index + 1}/{snapshot.total}): "
                    f"{first.error_message or '원인 미상'}"
                )
            if progress_callback is not None:
                completed_items = sum(
                    int(shard.payload.get("count", 0))
                    for shard in snapshot.shards
                    if shard.status == "succeeded"
                )
                running_jobs = sum(
                    shard.status == "running" for shard in snapshot.shards
                )
                queued_jobs = sum(
                    shard.status == "queued" for shard in snapshot.shards
                )
                signature = (snapshot.completed, running_jobs, queued_jobs)
                now = time.monotonic()
                if signature != last_progress_signature or now - last_reported_at >= 10:
                    progress_callback(
                        {
                            "phase": progress_phase,
                            "execution_mode": "kubernetes_shards",
                            "completed_batches": snapshot.completed,
                            "total_batches": snapshot.total,
                            "completed_items": completed_items,
                            "total_items": total_items,
                            "running_jobs": running_jobs,
                            "queued_jobs": queued_jobs,
                        }
                    )
                    last_progress_signature = signature
                    last_reported_at = now
            if snapshot.completed == snapshot.total:
                return snapshot
            if time.monotonic() >= deadline:
                raise ModuleExecutionError(
                    f"분산 ingestion shard 대기 시간이 초과되었습니다: {phase}"
                )
            time.sleep(self.poll_seconds)


__all__ = [
    "DistributedEmbeddingResult",
    "DistributedVectorCopyResult",
    "IngestionShardCoordinator",
]
