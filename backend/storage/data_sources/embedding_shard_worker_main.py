"""One-shot Kubernetes worker for a single Excel embedding shard."""

from __future__ import annotations

import logging
import os
import socket
import time
from typing import Any, cast
from uuid import uuid4

from backend.bootstrap.container import RuntimeContainer
from backend.engine.worker.lease import LeaseHeartbeat, terminate_process_on_lease_loss
from backend.storage.data_sources.ingestion_shards import (
    PostgresIngestionShardRepository,
)
from backend.storage.data_sources.shard_artifacts import IngestionShardArtifactStore
from modules.common.exceptions import ModuleExecutionError

logger = logging.getLogger(__name__)


def _worker_id() -> str:
    return os.getenv("KUBERNETES_JOB_NAME") or f"{socket.gethostname()}-{uuid4().hex[:12]}"


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


def _run(container: RuntimeContainer) -> int:
    repository = PostgresIngestionShardRepository(
        container.services.db_manager.database_url
    )
    worker_id = _worker_id()
    shard = repository.claim_next("embedding", worker_id)
    if shard is None:
        logger.info("claim 가능한 embedding shard가 없어 종료합니다")
        return 0
    payload = {**shard.payload, "shard_index": shard.shard_index}
    heartbeat = LeaseHeartbeat(
        lambda: repository.heartbeat(shard),
        interval_seconds=30,
        thread_name="ingestion-embedding-heartbeat",
        logger=logger,
        failure_message="embedding shard lease heartbeat 실패",
        on_lease_lost=terminate_process_on_lease_loss,
    )
    started = time.perf_counter()
    heartbeat.start()
    try:
        _, total_tokens = _encode_shard(container, payload)
        heartbeat.raise_if_lost()
        repository.complete(
            shard,
            total_tokens=total_tokens,
            duration_seconds=round(time.perf_counter() - started, 3),
        )
        logger.info(
            "embedding shard 완료 (operation=%s shard=%d count=%s)",
            shard.operation_id,
            shard.shard_index,
            shard.payload.get("count"),
        )
        return 0
    except Exception as error:
        logger.exception(
            "embedding shard 실패 (operation=%s shard=%d)",
            shard.operation_id,
            shard.shard_index,
        )
        repository.fail(shard, str(error))
        return 1
    finally:
        heartbeat.stop()


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
