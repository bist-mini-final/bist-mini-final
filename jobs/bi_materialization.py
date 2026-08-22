"""Declarative pipeline recipe for BI financial metrics analysis and snapshot creation."""

from __future__ import annotations

from .base import JobDefinition

BI_MATERIALIZATION_JOB = JobDefinition(
    job_id="bi_materialization",
    name="BI 기업 재무 메트릭 분석 및 대시보드 스냅샷 생성",
    description="기업별 재무제표 전수 질문 생성, RAG 검색, 수식 연산 및 시각화 대시보드 스냅샷 적재 파이프라인",
    queue_name="bi-materialization",
    module_sequence=[
        "company_entity_extractor",
        "decomposer",
        "embedder",
        "pgvector_retriever",
        "reader",
    ],
)

__all__ = ["BI_MATERIALIZATION_JOB"]
