"""One-shot Kubernetes worker for an idempotent pgvector COPY shard."""

from __future__ import annotations

import logging
import os
from typing import Any

from backend.bootstrap.container import RuntimeContainer
from backend.engine.worker.base import (
    LeasedWorker,
    WorkerLeaseSpec,
    default_worker_id,
)
from backend.storage.data_sources.ingestion_shards import (
    IngestionShard,
    PostgresIngestionShardRepository,
)
from backend.storage.data_sources.shard_artifacts import IngestionShardArtifactStore
from backend.storage.pgvector_store import PgVectorReplacePlan
from backend.storage.spreadsheets.langchain_document import lazy_cell_documents
from modules.common.exceptions import ModuleExecutionError

logger = logging.getLogger(__name__)


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


class VectorShardWorker(LeasedWorker[IngestionShard, None]):
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
        _copy_shard(self._container, payload)

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


def _run(container: RuntimeContainer) -> int:
    repository = PostgresIngestionShardRepository(
        container.services.db_manager.database_url
    )
    return VectorShardWorker(
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
