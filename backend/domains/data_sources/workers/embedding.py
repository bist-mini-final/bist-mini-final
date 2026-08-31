"""One-shot Kubernetes worker for a single Excel embedding shard."""

from __future__ import annotations

import logging

from backend.domains.data_sources.application.shard_ports import (
    EmbeddingShardExecutor,
    IngestionShardWorkerRepository,
)
from backend.domains.data_sources.domain import IngestionShard
from backend.shared.application.workers import (
    LeasedWorker,
    WorkerLeaseSpec,
    default_worker_id,
)

logger = logging.getLogger(__name__)


class EmbeddingShardWorker(LeasedWorker[IngestionShard, int]):
    def __init__(
        self,
        repository: IngestionShardWorkerRepository,
        executor: EmbeddingShardExecutor,
        worker_id: str,
    ) -> None:
        super().__init__(logger)
        self._repository = repository
        self._executor = executor
        self._worker_id = worker_id

    def claim(self) -> IngestionShard | None:
        return self._repository.claim_next("embedding", self._worker_id)

    def lease_spec(self, claim: IngestionShard) -> WorkerLeaseSpec:
        return WorkerLeaseSpec(
            job_id=f"{claim.operation_id}:embedding:{claim.shard_index}",
            worker_id=self._worker_id,
            renew=lambda: self._repository.heartbeat(claim),
            thread_name="ingestion-embedding-heartbeat",
            failure_message="embedding shard lease heartbeat 실패",
        )

    def execute(self, claim: IngestionShard) -> int:
        payload = {**claim.payload, "shard_index": claim.shard_index}
        return self._executor.execute(payload)

    def complete(
        self,
        claim: IngestionShard,
        output: int,
        duration_seconds: float,
    ) -> None:
        self._repository.complete(
            claim,
            total_tokens=output,
            duration_seconds=duration_seconds,
        )

    def fail(
        self,
        claim: IngestionShard,
        error: Exception,
        duration_seconds: float,
    ) -> None:
        self._repository.fail(claim, str(error))

    def empty_message(self) -> str:
        return "claim 가능한 embedding shard가 없어 종료합니다"

    def completed_message(self, claim: IngestionShard, output: int) -> str:
        return (
            f"embedding shard 완료 (operation={claim.operation_id} "
            f"shard={claim.shard_index} count={claim.payload.get('count')})"
        )

    def failed_message(self, claim: IngestionShard, error: Exception) -> str:
        return (
            f"embedding shard 실패 (operation={claim.operation_id} "
            f"shard={claim.shard_index})"
        )


def main(
    *,
    repository: IngestionShardWorkerRepository,
    executor: EmbeddingShardExecutor,
    worker_id: str | None = None,
) -> int:
    return EmbeddingShardWorker(
        repository,
        executor,
        worker_id or default_worker_id(),
    ).run_once()


__all__ = ["EmbeddingShardWorker", "main"]
