"""Declarative pipeline recipe for BI financial metrics analysis and snapshot creation."""

from __future__ import annotations

from .base import (
    DagJobDefinition,
    JobEdge,
    JobNode,
    KubernetesWorkerPolicy,
    WorkerJobDefinition,
)

# ---------------------------------------------------------------------------
# 1. Declarative Module DAG Pipeline for BI Metric Extraction
# ---------------------------------------------------------------------------
BI_METRIC_EXTRACTION_JOB = DagJobDefinition(
    job_id="bi_metric_extraction",
    name="BI 재무 메트릭 하이브리드 RAG 추출 파이프라인",
    description=(
        "기업 재무제표 엑셀 원본으로부터 catalog 범위 안에서 질문을 분해하고 "
        "pgvector HNSW 밀집 검색과 PostgreSQL FTS 키워드 검색 융합, "
        "컨텍스트 확장 및 근거 기반 수치 정규화 추출 모듈 조합 파이프라인"
    ),
    queue_name="workflow-core",
    version="2",
    nodes=(
        JobNode("query", "query_input"),
        JobNode("data-scope", "pgvector_data_scope"),
        JobNode("decompose", "decomposer"),
        JobNode("embed-query", "embedder"),
        JobNode("dense", "pgvector_retriever"),
        JobNode("keyword", "postgres_native_keyword_retriever"),
        JobNode("fuse", "rrf_fusion"),
        JobNode("expand-context", "pg_context_expander"),
        JobNode("read", "reader"),
    ),
    edges=(
        JobEdge("query-decompose", "query", "decompose", "query_context", "query_context"),
        JobEdge(
            "scope-decompose",
            "data-scope",
            "decompose",
            "scope_catalog",
            "scope_catalog",
        ),
        JobEdge(
            "decompose-embed",
            "decompose",
            "embed-query",
            "retrieval_plan",
            "retrieval_plan",
        ),
        JobEdge("embed-dense", "embed-query", "dense", "query_embeddings", "query_input"),
        JobEdge(
            "decompose-keyword",
            "decompose",
            "keyword",
            "retrieval_plan",
            "retrieval_plan",
        ),
        JobEdge("dense-fuse", "dense", "fuse", "dense_result", "dense_result"),
        JobEdge("keyword-fuse", "keyword", "fuse", "bm25_result", "bm25_result"),
        JobEdge("fuse-context", "fuse", "expand-context", "retrieval_json", "retrieval_json"),
        JobEdge("context-reader", "expand-context", "read", "context_json", "context_json"),
    ),
)

# ---------------------------------------------------------------------------
# 2. Kubernetes Queue Worker Jobs for Batch Orchestration
# ---------------------------------------------------------------------------
BI_MATERIALIZATION_JOB = WorkerJobDefinition(
    job_id="bi_materialization",
    name="BI 기업 재무 메트릭 분석 및 대시보드 스냅샷 생성",
    description=(
        "기업별 질문 work item을 하이브리드 RAG로 처리하고 계산·근거를 검증한 "
        "대시보드 스냅샷을 PostgreSQL에 적재합니다."
    ),
    queue_name="bi-materialization",
    worker_kind="bi-materialization",
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
    name="BI 재무 메트릭 질문 배치 처리",
    description=(
        "기업·기간·지표별 질문을 배치(기본 16개)로 묶어 BI_METRIC_EXTRACTION_JOB 모듈 체인과 "
        "병렬 스레드(기본 8개)로 처리하고 근거와 계산 결과를 PostgreSQL에 확정합니다. "
        "BI_QUESTION_BATCH_SIZE / BI_QUESTION_MAX_WORKERS 환경 변수로 튜닝 가능."
    ),
    queue_name="bi-question",
    worker_kind="bi-question",
    kubernetes=KubernetesWorkerPolicy(
        deployment_name="bi-question",
        # batch_size=16 x 최대 90초/질문 + 여유 = 2700 초
        active_deadline_seconds=2700,
        pending_query="""
            SELECT COUNT(*) FROM bi_questions
            WHERE status = 'queued'
               OR (status = 'running'
                   AND updated_at < NOW() - (180 * INTERVAL '1 second'))
        """,
    ),
    version="3",
)

__all__ = [
    "BI_MATERIALIZATION_JOB",
    "BI_METRIC_EXTRACTION_JOB",
    "BI_QUESTION_JOB",
]
