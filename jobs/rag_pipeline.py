"""Declarative pipeline recipe for standard end-to-end RAG query execution."""

from __future__ import annotations

from .base import JobDefinition

RAG_QUERY_JOB = JobDefinition(
    job_id="rag_query",
    name="하이브리드 재무 질의응답 RAG 파이프라인",
    description="자연어 질의 분해, 고밀도 pgvector + 키워드 RRF 융합 검색, 컨텍스트 확장 및 리더 답변 생성 파이프라인",
    queue_name="rag-query",
    module_sequence=[
        "query_input",
        "decomposer",
        "embedder",
        "pgvector_retriever",
        "postgres_native_keyword_retriever",
        "rrf_fusion",
        "context_expander",
        "reader",
    ],
)

__all__ = ["RAG_QUERY_JOB"]
