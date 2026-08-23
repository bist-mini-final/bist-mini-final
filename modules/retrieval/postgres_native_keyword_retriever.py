"""PostgreSQL full-text retrieval constrained by the router's scope plan."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from pydantic import Field

from backend.storage.pgvector_store import PgVectorStore
from modules.common.base_module import BaseModule, ModuleConfigDTO, ModuleDefinition, ModuleInputDTO
from modules.common.config import DEFAULT_RETRIEVAL_TOP_K
from modules.query.llm_query_router import RetrievalPlanDTO, document_context_for_plan
from modules.retrieval.pgvector_retriever import RankedSearchResultDTO


class PostgresNativeKeywordRetrieverInputDTO(ModuleInputDTO):
    retrieval_plan: RetrievalPlanDTO


class PostgresNativeKeywordRetrieverConfigDTO(ModuleConfigDTO):
    top_k: int = Field(default=DEFAULT_RETRIEVAL_TOP_K, gt=0, le=5000)


def _clean_tsquery_term(text: str) -> str:
    search_values: List[str] = []
    structured = False
    for segment in text.split("|"):
        if ":" not in segment:
            continue
        key, value = segment.split(":", 1)
        if key.strip().lower() not in {"row header", "column header", "cell value"}:
            continue
        structured = True
        normalized = value.strip()
        if normalized and normalized != "?":
            search_values.append(normalized)
    lexical = " ".join(search_values) if structured else text
    cleaned = re.sub(r"[^\w\s가-힣0-9]", " ", lexical)
    tokens = [token for token in cleaned.split() if token]
    return " ".join(tokens) if tokens else text.strip()


def _escape_like_term(text: str) -> str:
    return text.replace("!", "!!").replace("%", "!%").replace("_", "!_")


class PostgresNativeKeywordRetrieverModule(BaseModule):
    """Runs one FTS query per subquery across only its routed collections."""

    definition = ModuleDefinition(
        type="postgres_native_keyword_retriever",
        label="PostgreSQL Native Keyword Retriever",
        category="Logic",
        description=(
            "Router가 지정한 collection 집합 안에서만 GIN/tsvector 검색을 수행합니다."
        ),
        inputs=["retrieval_plan"],
        outputs=["bm25_result"],
        config_fields=["top_k"],
        raw_output=True,
        version="3",
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
        cfg = config or PostgresNativeKeywordRetrieverConfigDTO()
        plan = input_data.retrieval_plan
        document_context = document_context_for_plan(plan)
        if not plan.routes:
            return {
                "query_context": plan.query_context.model_dump(mode="json"),
                "document_context": document_context.model_dump(mode="json"),
                "items": [],
            }

        connection = self.pgvector_store._read_connection()
        hits_by_subquery: Dict[
            int, List[Tuple[float, str, Dict[str, Any], str, str]]
        ] = {}
        try:
            with connection.cursor() as cursor:
                for route in plan.routes:
                    query_text = route.subquery.text or route.subquery.to_serialized_query()
                    clean_query = _clean_tsquery_term(query_text)
                    if not clean_query:
                        continue
                    collection_ids = [scope.index_id for scope in route.collections]
                    where_extra: List[str] = []
                    where_params: List[Any] = []
                    if route.subquery.company not in ("", "?"):
                        company = route.subquery.company.strip()
                        where_extra.append(
                            "AND (embedding.cmetadata->>'company_name' ILIKE %s ESCAPE '!' "
                            "OR embedding.cmetadata->>'company_name' = %s)"
                        )
                        where_params.extend([f"%{_escape_like_term(company)}%", company])
                    if route.subquery.sheet not in ("", "?"):
                        where_extra.append(
                            "AND embedding.cmetadata->>'sheet_name' = %s"
                        )
                        where_params.append(route.subquery.sheet)
                    extra_sql = " ".join(where_extra)
                    sql = f"""
                        SELECT
                            embedding.document,
                            embedding.cmetadata,
                            ts_rank_cd(
                                to_tsvector('simple', embedding.document),
                                plainto_tsquery('simple', %s)
                            ) AS fts_score,
                            collection.name
                        FROM langchain_pg_embedding AS embedding
                        JOIN langchain_pg_collection AS collection
                          ON collection.uuid = embedding.collection_id
                        WHERE collection.name = ANY(%s)
                          AND to_tsvector('simple', embedding.document)
                              @@ plainto_tsquery('simple', %s)
                          {extra_sql}
                        ORDER BY fts_score DESC, embedding.id
                        LIMIT %s;
                    """
                    cursor.execute(
                        sql,
                        [clean_query, collection_ids, clean_query, *where_params, cfg.top_k],
                    )
                    rows = cursor.fetchall()
                    if not rows and extra_sql:
                        cursor.execute(
                            """
                            SELECT
                                embedding.document,
                                embedding.cmetadata,
                                ts_rank_cd(
                                    to_tsvector('simple', embedding.document),
                                    plainto_tsquery('simple', %s)
                                ) AS fts_score,
                                collection.name
                            FROM langchain_pg_embedding AS embedding
                            JOIN langchain_pg_collection AS collection
                              ON collection.uuid = embedding.collection_id
                            WHERE collection.name = ANY(%s)
                              AND to_tsvector('simple', embedding.document)
                                  @@ plainto_tsquery('simple', %s)
                            ORDER BY fts_score DESC, embedding.id
                            LIMIT %s;
                            """,
                            (clean_query, collection_ids, clean_query, cfg.top_k),
                        )
                        rows = cursor.fetchall()
                    route_hits = hits_by_subquery.setdefault(route.subquery_index, [])
                    for document, raw_metadata, score, index_id in rows:
                        metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
                        route_hits.append(
                            (
                                float(score) if score and float(score) > 0 else 0.05,
                                str(index_id),
                                metadata,
                                str(document),
                                query_text,
                            )
                        )
        finally:
            connection.close()

        ranked_items: List[Dict[str, Any]] = []
        for subquery_index in sorted(hits_by_subquery):
            seen: set[Tuple[str, str]] = set()
            rank = 0
            for score, index_id, metadata, document, query_text in sorted(
                hits_by_subquery[subquery_index],
                key=lambda hit: (-hit[0], hit[1]),
            ):
                company = str(metadata.get("company_name") or "")
                sheet = str(metadata.get("sheet_name") or "")
                coordinate = str(metadata.get("cell_coord") or "")
                raw_cell_id = str(metadata.get("cell_id") or f"{sheet}:{coordinate}")
                cell_id = (
                    f"{company}:{raw_cell_id}"
                    if company and not raw_cell_id.startswith(f"{company}:")
                    else raw_cell_id
                )
                key = (index_id, cell_id)
                if key in seen:
                    continue
                seen.add(key)
                rank += 1
                ranked_items.append(
                    {
                        "rank": rank,
                        "index_id": index_id,
                        "cell_id": cell_id,
                        "score": score,
                        "text": document,
                        "matched_subquery": query_text,
                    }
                )
                if rank >= cfg.top_k:
                    break

        return {
            "query_context": plan.query_context.model_dump(mode="json"),
            "document_context": document_context.model_dump(mode="json"),
            "items": ranked_items,
        }


__all__ = [
    "PostgresNativeKeywordRetrieverConfigDTO",
    "PostgresNativeKeywordRetrieverInputDTO",
    "PostgresNativeKeywordRetrieverModule",
    "_clean_tsquery_term",
    "_escape_like_term",
]
