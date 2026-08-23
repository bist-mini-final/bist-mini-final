"""PostgreSQL Native GIN FTS(전문 검색) 및 BM25 랭킹을 활용하는 희소(Sparse) 키워드 검색기 모듈.

서브쿼리 내 핵심 키워드 토큰을 추출하여 PostgreSQL의 `to_tsvector` 및 `plainto_tsquery` GIN 인덱스를 질의하고,
정확한 단어 매칭 및 텍스트 랭킹 점수(ts_rank) 기반 상위 Top-K 검색 후보를 반환합니다.

Example:
    Input DTO (입력 예시):
    ```json
    {
      "query_input": {
        "query_context": {"question_id": "q-001", "question_text": "삼성전자 영업이익"},
        "subqueries": [
          "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: ?"
        ]
      },
      "index_input": {
        "index_id": "rag_cells_a1b2c3d4",
        "file_name": "samsung_2023.xlsx",
        "workbook_hash": "a1b2c3d4...",
        "model": "text-embedding-3-large",
        "dimension": 3072,
        "document_count": 1200
      },
      "semantic_match": null
    }
    ```

    Output DTO (출력 예시):
    ```json
    {
      "query_context": {"question_id": "q-001", "question_text": "삼성전자 영업이익"},
      "document_context": {"file_name": "samsung_2023.xlsx", "workbook_hash": "a1b2c3d4..."},
      "items": [
        {
          "rank": 1,
          "cell_id": "IS_C5",
          "score": 0.825,
          "text": "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: 65670",
          "matched_subquery": "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: ?"
        }
      ]
    }
    ```
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple, Union

from pydantic import Field

from backend.storage.pgvector_store import PgVectorStore
from modules.common.base_module import (
    BaseModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleInputDTO,
)
from modules.common.config import DEFAULT_MIN_SCOPE_CONFIDENCE, DEFAULT_RETRIEVAL_TOP_K
from modules.query.decomposer import SubqueriesDTO
from modules.query.llm_query_router import LlmQueryRouterOutputDTO, RouterDecisionDTO
from modules.query.semantic_query_matcher import SemanticQueryMatchOutput
from modules.retrieval.pgvector_retriever import (
    RankedSearchResultDTO,
    extract_query_scope,
)
from modules.storage.pgvector_collection_loader import IndexOutputDTO

logger = logging.getLogger(__name__)


class PostgresNativeKeywordRetrieverInputDTO(ModuleInputDTO):
    query_input: SubqueriesDTO = Field(description="Thesaurus 또는 Decomposer에서 전달된 정밀 서브쿼리 목록")
    index_input: IndexOutputDTO = Field(
        description="pgvector Collection Loader가 전달한 대상 컬렉션 식별자"
    )
    semantic_match: Optional[
        Union[
            SemanticQueryMatchOutput,
            LlmQueryRouterOutputDTO,
            RouterDecisionDTO,
            Dict[str, Any],
        ]
    ] = Field(
        default=None,
        description="선택적 시맨틱 라우터 또는 LLM 라우터 결과 (company_name 및 sheet_names 스코프 사전 필터링용)",
    )


class PostgresNativeKeywordRetrieverConfigDTO(ModuleConfigDTO):
    top_k: int = Field(
        default=DEFAULT_RETRIEVAL_TOP_K,
        gt=0,
        le=5000,
        description="각 서브쿼리별 PostgreSQL GIN FTS 키워드 검색 최대 후보 개수",
    )
    min_scope_confidence: float = Field(
        default=DEFAULT_MIN_SCOPE_CONFIDENCE,
        ge=0,
        le=1,
        description="시맨틱 스코프 적용을 위한 최소 신뢰도 임계값",
    )


def _clean_tsquery_term(text: str) -> str:
    """Build lexical terms from the value-bearing fields of a structured query."""
    search_values: List[str] = []
    structured = False
    for segment in text.split("|"):
        if ":" not in segment:
            continue
        key, value = segment.split(":", 1)
        if key.strip().lower() not in {
            "row header",
            "column header",
            "cell value",
        }:
            continue
        structured = True
        normalized_value = value.strip()
        if normalized_value and normalized_value != "?":
            search_values.append(normalized_value)
    lexical_text = " ".join(search_values) if structured else text
    cleaned = re.sub(r"[^\w\s가-힣0-9]", " ", lexical_text)
    tokens = [t.strip() for t in cleaned.split() if len(t.strip()) >= 1]
    return " ".join(tokens) if tokens else text.strip()


def _escape_like_term(text: str) -> str:
    return text.replace("!", "!!").replace("%", "!%").replace("_", "!_")


class PostgresNativeKeywordRetrieverModule(BaseModule):
    """Executes high-speed keyword searches using PostgreSQL GIN index and tsvector ranking."""

    definition = ModuleDefinition(
        type="postgres_native_keyword_retriever",
        label="PostgreSQL Native Keyword Retriever",
        category="Logic",
        description="PostgreSQL GIN 인덱스와 tsvector 풀텍스트 검색을 활용하여 수 밀리초 내에 초고속 키워드 검색을 수행합니다.",
        inputs=["query_input", "index_input", "semantic_match"],
        outputs=["bm25_result"],
        config_fields=["top_k", "min_scope_confidence"],
        raw_output=True,
        version="2",
    )
    input_model = PostgresNativeKeywordRetrieverInputDTO
    config_model = PostgresNativeKeywordRetrieverConfigDTO
    output_model = RankedSearchResultDTO

    def __init__(self, pgvector_store: PgVectorStore) -> None:
        self.pgvector_store = pgvector_store

    def execute(
        self,
        input_data: PostgresNativeKeywordRetrieverInputDTO,
        config: Optional[PostgresNativeKeywordRetrieverConfigDTO] = None,
    ) -> Dict[str, Any]:
        """
        Executes PostgreSQL full-text search across selected collections for each subquery.
        """
        cfg = config or PostgresNativeKeywordRetrieverConfigDTO()
        raw_col_name = input_data.index_input.index_id
        target_collections = [c.strip() for c in raw_col_name.split(",") if c.strip()]
        if not target_collections:
            target_collections = [raw_col_name]
        top_k = cfg.top_k
        subqueries = [
            item.text or item.to_serialized_query()
            for item in input_data.query_input.items
        ]
        query_context_dict = input_data.query_input.query_context.model_dump(mode="json")
        doc_context_dict = {
            "file_name": input_data.index_input.file_name,
            "workbook_hash": input_data.index_input.workbook_hash,
            "index_id": input_data.index_input.index_id,
        }

        if not subqueries:
            return {
                "query_context": query_context_dict,
                "document_context": doc_context_dict,
                "items": [],
            }

        # Resolve semantic scopes if available (from Semantic Matcher or LLM Router)
        match_raw = input_data.semantic_match
        match: Any = getattr(match_raw, "semantic_match", match_raw)
        global_sheets: List[str] = []
        global_company: Optional[str] = None
        if match and match.matched and match.confidence >= cfg.min_scope_confidence:
            global_sheets = list(match.sheets or [])
            global_company = match.company_name

        conn = self.pgvector_store._read_connection()
        all_hits: List[Tuple[float, Dict[str, Any], str, str]] = []

        try:
            with conn.cursor() as cur:
                for sq in subqueries:
                    clean_q = _clean_tsquery_term(sq)
                    if not clean_q:
                        continue

                    # Dynamically extract per-subquery company and sheet scope
                    sq_company, sq_sheets = extract_query_scope(
                        sq,
                        fallback_company=global_company,
                        fallback_sheets=global_sheets,
                    )

                    where_extra: List[str] = []
                    where_params: List[Any] = []
                    if sq_company and isinstance(sq_company, str) and sq_company.strip():
                        clean_company = sq_company.strip()
                        escaped_company = _escape_like_term(clean_company)
                        where_extra.append(
                            "AND (cmetadata->>'company_name' ILIKE %s ESCAPE '!' "
                            "OR cmetadata->>'company_name' = %s)"
                        )
                        where_params.extend([f"%{escaped_company}%", clean_company])
                    if sq_sheets:
                        where_extra.append("AND (cmetadata->>'sheet_name' = ANY(%s))")
                        where_params.append(sq_sheets)

                    extra_sql = " ".join(where_extra)

                    sql = f"""
                        SELECT
                            id,
                            document,
                            cmetadata,
                            ts_rank_cd(to_tsvector('simple', document), plainto_tsquery('simple', %s)) AS fts_score,
                            collection_id
                        FROM langchain_pg_embedding
                        WHERE collection_id IN (
                                SELECT uuid
                                FROM langchain_pg_collection
                                WHERE name = ANY(%s)
                              )
                          AND to_tsvector('simple', document) @@ plainto_tsquery('simple', %s)
                          {extra_sql}
                        ORDER BY fts_score DESC, id
                        LIMIT %s;
                    """
                    full_params = [
                        clean_q,
                        target_collections,
                        clean_q,
                        *where_params,
                        top_k,
                    ]
                    cur.execute(sql, full_params)
                    rows = cur.fetchall()

                    # Preserve recall by removing only metadata scope constraints.
                    if not rows and extra_sql:
                        relaxed_sql = """
                            SELECT
                                id,
                                document,
                                cmetadata,
                                ts_rank_cd(to_tsvector('simple', document), plainto_tsquery('simple', %s)) AS fts_score,
                                collection_id
                            FROM langchain_pg_embedding
                            WHERE collection_id IN (
                                    SELECT uuid
                                    FROM langchain_pg_collection
                                    WHERE name = ANY(%s)
                                  )
                              AND to_tsvector('simple', document) @@ plainto_tsquery('simple', %s)
                            ORDER BY fts_score DESC, id
                            LIMIT %s;
                        """
                        cur.execute(
                            relaxed_sql,
                            (clean_q, target_collections, clean_q, top_k),
                        )
                        rows = cur.fetchall()

                    for r in rows:
                        _, doc_text, cmeta, score, _ = r
                        cmeta_dict = cmeta if isinstance(cmeta, dict) else {}
                        final_score = float(score) if score and float(score) > 0 else 0.05
                        all_hits.append((final_score, cmeta_dict, doc_text, sq))
        finally:
            conn.close()

        ranked_items: List[Dict[str, Any]] = []
        for subquery in subqueries:
            seen_cell_ids = set()
            subquery_hits = sorted(
                (hit for hit in all_hits if hit[3] == subquery),
                key=lambda item: item[0],
                reverse=True,
            )
            for score, cmeta, doc_text, _ in subquery_hits:
                company = cmeta.get("company_name", "")
                cell_coord = cmeta.get("cell_coord", "")
                sheet = cmeta.get("sheet_name", "")
                raw_cell_id = cmeta.get("cell_id") or f"{sheet}:{cell_coord}"
                cell_id = (
                    f"{company}:{raw_cell_id}"
                    if company and not str(raw_cell_id).startswith(f"{company}:")
                    else str(raw_cell_id)
                )
                if cell_id in seen_cell_ids:
                    continue
                seen_cell_ids.add(cell_id)
                ranked_items.append(
                    {
                        "rank": len(seen_cell_ids),
                        "cell_id": cell_id,
                        "score": score,
                        "text": doc_text,
                        "matched_subquery": subquery,
                    }
                )

        return {
            "query_context": query_context_dict,
            "document_context": doc_context_dict,
            "items": ranked_items,
        }
