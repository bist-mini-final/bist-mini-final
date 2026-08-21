"""PostgreSQL Native GIN Full-Text Keyword Search Module."""

from __future__ import annotations

import logging
import re
from typing import Optional, Any, Dict, List, Optional, Tuple, cast

from pydantic import BaseModel, Field

from backend.storage.pgvector_store import PgVectorStore
from modules.common.base_module import (
    BaseModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleExecutionError,
    ModuleInputDTO,
)
from modules.query.decomposer import SubqueriesDTO
from modules.storage.pgvector_collection_loader import IndexOutputDTO
from modules.retrieval.retrieval_models import RankedSearchCandidateDTO, RankedSearchResultDTO

logger = logging.getLogger(__name__)


class PostgresNativeKeywordRetrieverInputDTO(ModuleInputDTO):
    query_input: SubqueriesDTO = Field(description="Thesaurus 또는 Decomposer에서 전달된 정밀 서브쿼리 목록")
    index_input: IndexOutputDTO = Field(
        description="pgvector Collection Loader가 전달한 대상 컬렉션 식별자"
    )


class PostgresNativeKeywordRetrieverConfigDTO(ModuleConfigDTO):
    top_k: int = Field(
        default=100,
        gt=0,
        le=5000,
        description="각 서브쿼리별 PostgreSQL GIN FTS 키워드 검색 최대 후보 개수",
    )


class PostgresNativeKeywordRetrieverExecutionDTO(
    PostgresNativeKeywordRetrieverInputDTO, PostgresNativeKeywordRetrieverConfigDTO
):
    """Internal union of search inputs and retrieval policy."""


def _clean_tsquery_term(text: str) -> str:
    """Clean query text into terms suitable for PostgreSQL plainto_tsquery."""
    cleaned = re.sub(r"[^\w\s가-힣0-9]", " ", text)
    tokens = [t.strip() for t in cleaned.split() if len(t.strip()) >= 1]
    return " ".join(tokens) if tokens else text.strip()


class PostgresNativeKeywordRetrieverModule(BaseModule):
    """Executes high-speed keyword searches using PostgreSQL GIN index and tsvector ranking."""

    definition = ModuleDefinition(
        type="postgres_native_keyword_retriever",
        label="PostgreSQL Native Keyword Retriever",
        category="Logic",
        description="PostgreSQL GIN 인덱스와 tsvector 풀텍스트 검색을 활용하여 수 밀리초 내에 초고속 키워드 검색을 수행합니다.",
        inputs=["query_input", "index_input"],
        outputs=["bm25_result"],
        config_fields=["top_k"],
        raw_output=True,
        version="1",
    )
    input_model = PostgresNativeKeywordRetrieverInputDTO
    config_model = PostgresNativeKeywordRetrieverConfigDTO
    execution_model = PostgresNativeKeywordRetrieverExecutionDTO
    output_model = RankedSearchResultDTO

    def __init__(self, pgvector_store: Optional[PgVectorStore] = None) -> None:
        self.pgvector_store = pgvector_store or PgVectorStore()

    def execute(
        self,
        input_data: PostgresNativeKeywordRetrieverInputDTO,
        config: Optional[PostgresNativeKeywordRetrieverConfigDTO] = None,
    ) -> Dict[str, Any]:
        """
        Executes PostgreSQL full-text search across selected collections for each subquery.
        """
        if config is None and isinstance(input_data, PostgresNativeKeywordRetrieverExecutionDTO):
            cfg = input_data
        else:
            cfg = config or PostgresNativeKeywordRetrieverConfigDTO()
        raw_col_name = input_data.index_input.index_id
        target_collections = [c.strip() for c in raw_col_name.split(",") if c.strip()]
        if not target_collections:
            target_collections = [raw_col_name]
        top_k = cfg.top_k
        subqueries = input_data.query_input.subqueries
        query_context_dict = input_data.query_input.query_context.model_dump(mode="json")
        doc_context_dict = {
            "file_name": input_data.index_input.file_name,
            "workbook_hash": input_data.index_input.workbook_hash,
        }

        if not subqueries:
            return {
                "query_context": query_context_dict,
                "document_context": doc_context_dict,
                "items": [],
            }

        conn = self.pgvector_store._raw_connection()
        all_hits: List[Tuple[float, Dict[str, Any], str, str]] = []

        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT uuid, name FROM langchain_pg_collection WHERE name = ANY(%s);",
                    (target_collections,),
                )
                col_rows = cur.fetchall()
                col_map = {name: str(u) for u, name in col_rows}
                col_uuids = list(col_map.values())

                if not col_uuids:
                    logger.warning("PostgresNativeKeywordRetriever: 컬렉션을 찾을 수 없음: %s", target_collections)
                    return {
                        "query_context": query_context_dict,
                        "document_context": doc_context_dict,
                        "items": [],
                    }

                for sq in subqueries:
                    clean_q = _clean_tsquery_term(sq)
                    if not clean_q:
                        continue

                    sql = """
                        SELECT 
                            id,
                            document,
                            cmetadata,
                            ts_rank_cd(to_tsvector('simple', document), plainto_tsquery('simple', %s)) AS fts_score,
                            collection_id
                        FROM langchain_pg_embedding
                        WHERE collection_id::text = ANY(%s)
                          AND to_tsvector('simple', document) @@ plainto_tsquery('simple', %s)
                        ORDER BY fts_score DESC, id
                        LIMIT %s;
                    """
                    cur.execute(sql, (clean_q, col_uuids, clean_q, top_k))
                    rows = cur.fetchall()

                    for r in rows:
                        doc_id, doc_text, cmeta, score, _ = r
                        cmeta_dict = cmeta if isinstance(cmeta, dict) else {}
                        final_score = float(score) if score and float(score) > 0 else 0.05
                        all_hits.append((final_score, cmeta_dict, doc_text, sq))

        except Exception as e:
            logger.exception("PostgresNativeKeywordRetriever 실행 실패: %s", e)
            raise ModuleExecutionError(f"PostgreSQL FTS 키워드 검색 실패: {e}") from e
        finally:
            conn.close()

        ranked_items: List[Dict[str, Any]] = []
        seen_keys = set()
        rank_counter = 1

        for score, cmeta, doc_text, matched_sq in sorted(all_hits, key=lambda x: x[0], reverse=True):
            company = cmeta.get("company_name", "")
            cell_coord = cmeta.get("cell_coord", "")
            sheet = cmeta.get("sheet_name", "")
            raw_cell_id = cmeta.get("cell_id") or f"{sheet}:{cell_coord}"
            cell_id = f"{company}:{raw_cell_id}" if company and not str(raw_cell_id).startswith(f"{company}:") else str(raw_cell_id)

            key = (cell_id, matched_sq)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            ranked_items.append(
                {
                    "rank": rank_counter,
                    "cell_id": cell_id,
                    "score": score,
                    "text": doc_text,
                    "matched_subquery": matched_sq,
                }
            )
            rank_counter += 1

        return {
            "query_context": query_context_dict,
            "document_context": doc_context_dict,
            "items": ranked_items,
        }
