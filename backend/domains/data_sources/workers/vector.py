"""One-shot Kubernetes worker for an idempotent pgvector COPY shard."""

from __future__ import annotations

import logging

from backend.domains.data_sources.application.shard_ports import (
    IngestionShardWorkerRepository,
    VectorShardExecutor,
)
from backend.domains.data_sources.domain import IngestionShard
from backend.shared.application.workers import (
    LeasedWorker,
    WorkerLeaseSpec,
    default_worker_id,
)

logger = logging.getLogger(__name__)


class VectorShardWorker(LeasedWorker[IngestionShard, None]):
    def __init__(
        self,
        repository: IngestionShardWorkerRepository,
        executor: VectorShardExecutor,
        worker_id: str,
    ) -> None:
        super().__init__(logger)
        self._repository = repository
        self._executor = executor
        self._worker_id = worker_id

    def claim(self) -> IngestionShard | None:
        return self._repository.claim_next("vector_copy", self._worker_id)

    def lease_spec(self, claim: IngestionShard) -> WorkerLeaseSpec:
        return WorkerLeaseSpec(
            job_id=f"{claim.operation_id}:vector_copy:{claim.shard_index}",
            worker_id=self._worker_id,
            renew=lambda: self._repository.heartbeat(claim),
            thread_name="ingestion-vector-heartbeat",
            failure_message="vector COPY shard lease heartbeat 실패",
        )

    def execute(self, claim: IngestionShard) -> None:
        payload = {**claim.payload, "shard_index": claim.shard_index}
        self._executor.execute(payload)

    def complete(
        self,
        claim: IngestionShard,
        output: None,
        duration_seconds: float,
    ) -> None:
        self._repository.complete(claim, duration_seconds=duration_seconds)

    def fail(
        self,
        claim: IngestionShard,
        error: Exception,
        duration_seconds: float,
    ) -> None:
        self._repository.fail(claim, str(error))

    def empty_message(self) -> str:
        return "claim 가능한 vector COPY shard가 없어 종료합니다"

    def completed_message(self, claim: IngestionShard, output: None) -> str:
        return (
            f"vector COPY shard 완료 (operation={claim.operation_id} "
            f"shard={claim.shard_index} count={claim.payload.get('count')})"
        )

    def failed_message(self, claim: IngestionShard, error: Exception) -> str:
        return (
            f"vector COPY shard 실패 (operation={claim.operation_id} "
            f"shard={claim.shard_index})"
        )


def main(
    *,
    repository: IngestionShardWorkerRepository,
    executor: VectorShardExecutor,
    worker_id: str | None = None,
) -> int:
    return VectorShardWorker(
        repository,
        executor,
        worker_id or default_worker_id(),
    ).run_once()


__all__ = ["VectorShardWorker", "main"]
