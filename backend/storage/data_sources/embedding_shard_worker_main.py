"""One-shot Kubernetes worker for a single Excel embedding shard."""

from __future__ import annotations

import logging
import os
from typing import Any, cast

from backend.bootstrap.application import RuntimeContainer
from backend.shared.application.workers import (
    LeasedWorker,
    WorkerLeaseSpec,
    default_worker_id,
)
from backend.storage.data_sources.ingestion_shards import (
    IngestionShard,
    PostgresIngestionShardRepository,
)
from backend.storage.data_sources.shard_artifacts import IngestionShardArtifactStore
from modules.common.exceptions import ModuleExecutionError

logger = logging.getLogger(__name__)


def _encode_shard(container: RuntimeContainer, payload: dict[str, Any]) -> tuple[list[list[float]], int]:
    artifact_id = str(payload["artifact_id"])
    shard_index = int(payload["shard_index"])
    dimension = int(payload["dimension"])
    model_name = str(payload["model"])
    batch_size = int(payload["batch_size"])
    expected_count = int(payload["count"])

    artifact_store = container.services.module_registry.embedding_artifact_store
    shards = IngestionShardArtifactStore(artifact_store)
    items = shards.read_manifest(artifact_id, shard_index)
    texts = [str(item.get("text") or "") for item in items]
    if len(texts) != expected_count or any(not text for text in texts):
        raise ModuleExecutionError("embedding shard manifest의 문서 개수가 올바르지 않습니다")

    encoder = container.embedding_encoder
    encoder_adapter = cast(Any, encoder)
    encode_for_model = getattr(encoder_adapter, "encode_for_model", None)
    vectors = cast(
        list[list[float]],
        (
            encode_for_model(texts, model_name, batch_size)
            if callable(encode_for_model)
            else encoder_adapter.encode(texts)
        ),
    )
    if len(vectors) != expected_count or any(len(vector) != dimension for vector in vectors):
        raise ModuleExecutionError("embedding shard 결과의 개수 또는 차원이 올바르지 않습니다")
    shards.put_vector_shard(
        artifact_id,
        shard_index,
        vectors,
        dimension=dimension,
    )
    usage = getattr(encoder, "last_usage", None)
    total_tokens = int(usage.get("total_tokens", 0) or 0) if isinstance(usage, dict) else 0
    return vectors, total_tokens


class EmbeddingShardWorker(LeasedWorker[IngestionShard, int]):
    def __init__(
        self,
        container: RuntimeContainer,
        repository: PostgresIngestionShardRepository,
        worker_id: str,
    ) -> None:
        super().__init__(logger)
        self._container = container
        self._repository = repository
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
        _, total_tokens = _encode_shard(self._container, payload)
        return total_tokens

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


def _run(container: RuntimeContainer) -> int:
    repository = PostgresIngestionShardRepository(
        container.services.db_manager.database_url
    )
    return EmbeddingShardWorker(
        container,
        repository,
        default_worker_id(),
    ).run_once()


def main() -> int:
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    with RuntimeContainer.create(
        initialize_schema=False,
        require_database=True,
    ) as container:
        return _run(container)


if __name__ == "__main__":
    raise SystemExit(main())
