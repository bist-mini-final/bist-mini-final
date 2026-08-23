"""Declarative pipeline recipe for standard end-to-end RAG query execution."""

from __future__ import annotations

from .base import DagJobDefinition, JobEdge, JobNode

RAG_QUERY_JOB = DagJobDefinition(
    job_id="rag_query",
    name="하이브리드 재무 질의응답 RAG 파이프라인",
    description=(
        "질의 라우팅/분해, pgvector HNSW와 PostgreSQL FTS 병렬 검색, "
        "RRF 융합, 컨텍스트 확장 및 근거 기반 답변 생성 파이프라인"
    ),
    queue_name="workflow-core",
    version="3",
    nodes=(
        JobNode("query", "query_input"),
        JobNode("route", "llm_query_router"),
        JobNode("decompose", "decomposer"),
        JobNode("load-index", "pgvector_collection_loader"),
        JobNode("embed-query", "embedder"),
        JobNode("dense", "pgvector_retriever"),
        JobNode("keyword", "postgres_native_keyword_retriever"),
        JobNode("fuse", "rrf_fusion"),
        JobNode("expand-context", "pg_context_expander"),
        JobNode("read", "reader"),
    ),
    edges=(
        JobEdge("query-route", "query", "route", "query_context", "query_context"),
        JobEdge("query-decompose", "query", "decompose", "query_context", "query_context"),
        JobEdge("route-decompose", "route", "decompose", "semantic_match", "semantic_match"),
        JobEdge(
            "decompose-embed",
            "decompose",
            "embed-query",
            "output",
            "query_input",
        ),
        JobEdge(
            "index-embed",
            "load-index",
            "embed-query",
            "index_output",
            "index_input",
        ),
        JobEdge(
            "embed-dense",
            "embed-query",
            "dense",
            "query_embeddings",
            "query_input",
        ),
        JobEdge("index-dense", "load-index", "dense", "index_output", "index_input"),
        JobEdge("route-dense", "route", "dense", "semantic_match", "semantic_match"),
        JobEdge("decompose-keyword", "decompose", "keyword", "output", "query_input"),
        JobEdge("index-keyword", "load-index", "keyword", "index_output", "index_input"),
        JobEdge("route-keyword", "route", "keyword", "semantic_match", "semantic_match"),
        JobEdge("dense-fuse", "dense", "fuse", "dense_result", "dense_result"),
        JobEdge("keyword-fuse", "keyword", "fuse", "bm25_result", "bm25_result"),
        JobEdge("fuse-context", "fuse", "expand-context", "retrieval_json", "retrieval_json"),
        JobEdge("context-reader", "expand-context", "read", "context_json", "context_json"),
    ),
)

__all__ = ["RAG_QUERY_JOB"]
