"""Declarative Kubernetes benchmark coordinator job."""

from __future__ import annotations

from .base import KubernetesWorkerPolicy, WorkerJobDefinition

BENCHMARK_JOB = WorkerJobDefinition(
    job_id="benchmark",
    name="RAG 비교 벤치마크",
    description=(
        "비교 대상 workflow run을 Kubernetes 큐에 순차 제출하고 정확도·지연·"
        "비용을 채점해 PostgreSQL 결과로 확정합니다."
    ),
    queue_name="benchmark",
    worker_kind="benchmark",
    kubernetes=KubernetesWorkerPolicy(
        deployment_name="benchmark",
        mount_data_volume=True,
        pending_query="""
            SELECT COUNT(*) FROM benchmark_jobs
            WHERE (status = 'queued' AND available_at <= NOW())
               OR (status IN ('running', 'pausing', 'cancelling')
                   AND (heartbeat_at IS NULL
                        OR heartbeat_at < NOW() - (180 * INTERVAL '1 second')))
        """,
    ),
    version="2",
)

__all__ = ["BENCHMARK_JOB"]
