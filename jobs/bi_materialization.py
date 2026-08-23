"""Declarative pipeline recipe for BI financial metrics analysis and snapshot creation."""

from __future__ import annotations

from .base import KubernetesWorkerPolicy, WorkerJobDefinition

BI_MATERIALIZATION_JOB = WorkerJobDefinition(
    job_id="bi_materialization",
    name="BI 기업 재무 메트릭 분석 및 대시보드 스냅샷 생성",
    description=(
        "기업별 질문 work item을 하이브리드 RAG로 처리하고 계산·근거를 검증한 "
        "대시보드 스냅샷을 PostgreSQL에 적재합니다."
    ),
    queue_name="bi-materialization",
    worker_entrypoint="backend.features.bi.materialization_worker_main:main",
    kubernetes=KubernetesWorkerPolicy(
        deployment_name="bi-materialization",
        pending_query="""
            SELECT COUNT(*) FROM bi_materialization_jobs
            WHERE (status = 'queued' AND available_at <= NOW())
               OR (status IN ('profiling', 'extracting')
                   AND (heartbeat_at IS NULL
                        OR heartbeat_at < NOW() - (180 * INTERVAL '1 second')))
        """,
    ),
    version="2",
)

BI_QUESTION_JOB = WorkerJobDefinition(
    job_id="bi_question",
    name="BI 재무 메트릭 질문 처리",
    description=(
        "기업·기간·지표별 질문을 하이브리드 RAG로 병렬 처리하고 근거와 "
        "계산 결과를 PostgreSQL에 확정합니다."
    ),
    queue_name="bi-question",
    worker_entrypoint="backend.features.bi.question_worker_main:main",
    kubernetes=KubernetesWorkerPolicy(
        deployment_name="bi-question",
        active_deadline_seconds=900,
        pending_query="""
            SELECT COUNT(*) FROM bi_questions
            WHERE status = 'queued'
               OR (status = 'running'
                   AND updated_at < NOW() - (180 * INTERVAL '1 second'))
        """,
    ),
    version="2",
)

__all__ = ["BI_MATERIALIZATION_JOB", "BI_QUESTION_JOB"]
