"""KEDA worker recipes for distributed Excel-ingestion shard phases."""

from __future__ import annotations

from .base import KubernetesWorkerPolicy, WorkerJobDefinition

INGESTION_EMBEDDING_SHARD_JOB = WorkerJobDefinition(
    job_id="ingestion_embedding_shard",
    name="Excel 문서 임베딩 샤드",
    description=(
        "직렬화된 Excel 문서를 API 배치 단위로 claim하여 독립적으로 임베딩하고 "
        "공유 float32 part artifact를 생성합니다."
    ),
    queue_name="ingestion-embedding",
    worker_entrypoint=(
        "backend.storage.data_sources.embedding_shard_worker_main:main"
    ),
    kubernetes=KubernetesWorkerPolicy(
        deployment_name="ingestion-embedding",
        active_deadline_seconds=900,
        mount_data_volume=True,
        max_replica_count=4,
        pending_query="""
            SELECT COUNT(*) FROM ingestion_shards
            WHERE phase = 'embedding'
              AND ((status = 'queued' AND available_at <= NOW())
                OR (status = 'running' AND (heartbeat_at IS NULL
                  OR heartbeat_at < NOW() - (180 * INTERVAL '1 second'))))
        """,
    ),
)

INGESTION_VECTOR_SHARD_JOB = WorkerJobDefinition(
    job_id="ingestion_vector_shard",
    name="Excel pgvector COPY 샤드",
    description=(
        "완료된 임베딩 artifact의 범위를 결정적 행 ID로 staging collection에 "
        "Binary COPY하고 재시도 시 동일 범위만 교체합니다."
    ),
    queue_name="ingestion-vector",
    worker_entrypoint="backend.storage.data_sources.vector_shard_worker_main:main",
    kubernetes=KubernetesWorkerPolicy(
        deployment_name="ingestion-vector",
        active_deadline_seconds=1800,
        mount_data_volume=True,
        max_replica_count=2,
        pending_query="""
            SELECT COUNT(*) FROM ingestion_shards
            WHERE phase = 'vector_copy'
              AND ((status = 'queued' AND available_at <= NOW())
                OR (status = 'running' AND (heartbeat_at IS NULL
                  OR heartbeat_at < NOW() - (180 * INTERVAL '1 second'))))
        """,
    ),
)

__all__ = ["INGESTION_EMBEDDING_SHARD_JOB", "INGESTION_VECTOR_SHARD_JOB"]
