"""One-shot Kubernetes worker for an idempotent pgvector COPY shard."""

from __future__ import annotations

import logging
import os
import socket
import time
from typing import Any
from uuid import uuid4

from backend.bootstrap.container import RuntimeContainer
from backend.engine.worker.lease import LeaseHeartbeat, terminate_process_on_lease_loss
from backend.storage.data_sources.ingestion_shards import (
    PostgresIngestionShardRepository,
)
from backend.storage.data_sources.shard_artifacts import IngestionShardArtifactStore
from backend.storage.pgvector_store import PgVectorReplacePlan
from backend.storage.spreadsheets.langchain_document import lazy_cell_documents
from modules.common.exceptions import ModuleExecutionError

logger = logging.getLogger(__name__)


def _worker_id() -> str:
    return os.getenv("KUBERNETES_JOB_NAME") or f"{socket.gethostname()}-{uuid4().hex[:12]}"


def _copy_shard(container: RuntimeContainer, payload: dict[str, Any]) -> None:
    artifact_id = str(payload["artifact_id"])
    shard_index = int(payload["shard_index"])
    start = int(payload["start"])
    stop = int(payload["stop"])
    count = int(payload["count"])
    dimension = int(payload["dimension"])
    metadata = dict(payload["metadata"])
    if stop - start != count:
        raise ModuleExecutionError("vector COPY shard 범위가 올바르지 않습니다")

    artifact_store = container.services.module_registry.embedding_artifact_store
    shards = IngestionShardArtifactStore(artifact_store)
    items = shards.read_manifest(artifact_id, shard_index)
    if len(items) != count:
        raise ModuleExecutionError("vector COPY shard manifest 개수가 올바르지 않습니다")
    vectors = artifact_store.vector_range_sequence(
        artifact_id,
        start,
        stop,
        int(metadata["document_count"]),
        dimension,
    )
    documents = lazy_cell_documents(
        items=items,
        file_name=str(metadata.get("file_name") or ""),
        workbook_hash=str(metadata.get("workbook_hash") or ""),
        index_id=str(payload["index_id"]),
        company_name=str(metadata.get("company_name") or ""),
    )
    plan = PgVectorReplacePlan(
        index_id=str(payload["index_id"]),
        operation_id=str(payload["operation_id"]),
        staging_name=str(payload["staging_name"]),
        staging_uuid=str(payload["staging_uuid"]),
        dimension=dimension,
        metadata=metadata,
    )
    container.services.pgvector_store.copy_prepared_collection_shard(
        plan,
        documents=documents,
        vectors=vectors,
        start_index=start,
    )


def _run(container: RuntimeContainer) -> int:
    repository = PostgresIngestionShardRepository(
        container.services.db_manager.database_url
    )
    worker_id = _worker_id()
    shard = repository.claim_next("vector_copy", worker_id)
    if shard is None:
        logger.info("claim 가능한 vector COPY shard가 없어 종료합니다")
        return 0
    payload = {**shard.payload, "shard_index": shard.shard_index}
    heartbeat = LeaseHeartbeat(
        lambda: repository.heartbeat(shard),
        interval_seconds=30,
        thread_name="ingestion-vector-heartbeat",
        logger=logger,
        failure_message="vector COPY shard lease heartbeat 실패",
        on_lease_lost=terminate_process_on_lease_loss,
    )
    started = time.perf_counter()
    heartbeat.start()
    try:
        _copy_shard(container, payload)
        heartbeat.raise_if_lost()
        repository.complete(
            shard,
            duration_seconds=round(time.perf_counter() - started, 3),
        )
        logger.info(
            "vector COPY shard 완료 (operation=%s shard=%d count=%s)",
            shard.operation_id,
            shard.shard_index,
            shard.payload.get("count"),
        )
        return 0
    except Exception as error:
        logger.exception(
            "vector COPY shard 실패 (operation=%s shard=%d)",
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
