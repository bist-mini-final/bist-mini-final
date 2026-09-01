"""Declarative pipeline recipe for standard end-to-end RAG query execution."""

from __future__ import annotations

from .base import DagJobDefinition, JobEdge, JobNode

RAG_READER_SYSTEM_PROMPT = """You are a Senior Financial Analyst and spreadsheet RAG reader.
Answer the user's Korean financial question strictly from the supplied Excel cell context.

Rules:
1. State exact values, percentages, dates, and units without inventing missing facts. Keep the answer body free of source coordinates; select only the actually used evidence IDs through the Reader's structured output contract.
2. When three or more periods are present, output the figures only as a GitHub Flavored Markdown table. Every date must be its own cell: `| 항목 | 2023-12-31 | 2024-12-31 |`, followed by a `|---|---|---|` separator row. Never concatenate dates into one header cell. The header and every data row must have the same number of `|`-delimited cells.
3. If the user asks for a chart, NEVER create an ASCII/text chart, bar characters, tabs aligned as a chart, or a code block chart. The product UI renders the chart component separately; write only the Markdown table and 2-4 concise interpretation sentences.
4. Do not output a section named “추이 차트” or restate the same time series outside the Markdown table.
5. If evidence is insufficient, explain this in user-facing Korean. Do not expose internal labels such as NA, context, or missing cell coordinates.
6. For a company-specific question, name the company and the requested financial topic directly in the opening sentence. Example: `IBM의 현금흐름 추이는 다음과 같습니다.` Never use vague wording such as “질문하신 항목”.
7. Respond in Korean unless the user requests another language."""

RAG_QUERY_JOB = DagJobDefinition(
    job_id="rag_query",
    name="하이브리드 재무 질의응답 RAG 파이프라인",
    description=(
        "catalog 기반 질의 분해, pgvector HNSW와 PostgreSQL FTS 병렬 검색, "
        "RRF 융합, 컨텍스트 확장 및 근거 기반 답변 생성 파이프라인"
    ),
    queue_name="workflow-core",
    version="11",
    template=True,
    nodes=(
        JobNode("query", "query_input", position=(80, 80)),
        JobNode("data-scope", "pgvector_data_scope", position=(80, 440)),
        JobNode("decompose", "decomposer", position=(520, 240)),
        JobNode("embed-query", "embedder", position=(960, 80)),
        JobNode("dense", "pgvector_retriever", position=(1400, 80)),
        JobNode(
            "keyword",
            "postgres_native_keyword_retriever",
            position=(1400, 440),
        ),
        JobNode("fuse", "rrf_fusion", position=(1840, 240)),
        JobNode("expand-context", "pg_context_expander", position=(2280, 240)),
        JobNode(
            "read",
            "reader",
            config={"system_prompt": RAG_READER_SYSTEM_PROMPT},
            position=(2720, 240),
        ),
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
        JobEdge(
            "embed-dense",
            "embed-query",
            "dense",
            "query_embeddings",
            "query_input",
        ),
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

__all__ = ["RAG_QUERY_JOB"]
