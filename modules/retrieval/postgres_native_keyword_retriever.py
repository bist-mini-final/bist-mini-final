"""PostgreSQL full-text retrieval constrained by the router's scope plan."""

from __future__ import annotations

import asyncio
import re
from typing import Any, Dict, List, Optional, Tuple

from pydantic import Field

from modules.common.base_module import BaseModule, ModuleConfigDTO, ModuleDefinition, ModuleInputDTO
from modules.common.config import DEFAULT_RETRIEVAL_TOP_K
from modules.query.llm_query_router import RetrievalPlanDTO, document_context_for_plan
from modules.retrieval.pgvector_retriever import RankedSearchResultDTO
from modules.retrieval.ports import KeywordSearchPort


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
        description=("Router가 지정한 collection 집합 안에서만 GIN/tsvector 검색을 수행합니다."),
        inputs=["retrieval_plan"],
        outputs=["bm25_result"],
        config_fields=["top_k"],
        raw_output=True,
        version="3",
    )
    input_model = PostgresNativeKeywordRetrieverInputDTO
    config_model = PostgresNativeKeywordRetrieverConfigDTO
    output_model = RankedSearchResultDTO

    def __init__(self, pgvector_store: KeywordSearchPort) -> None:
        self.pgvector_store = pgvector_store

    def _search_one(
        self,
        route: Any,
        top_k: int,
    ) -> Tuple[int, str, List[Tuple[str, Dict[str, Any], float, str]]]:
        query_text = route.subquery.text or route.subquery.to_serialized_query()
        clean_query = _clean_tsquery_term(query_text)
        if not clean_query:
            return route.subquery_index, query_text, []
        rows = self.pgvector_store.keyword_search(
            collection_names=[scope.index_id for scope in route.collections],
            query_text=clean_query,
            k=top_k,
            company_name=(
                route.subquery.company.strip() if route.subquery.company not in ("", "?") else None
            ),
            sheet_name=(route.subquery.sheet if route.subquery.sheet not in ("", "?") else None),
        )
        return route.subquery_index, query_text, rows

    async def _search_one_async(
        self,
        route: Any,
        top_k: int,
    ) -> Tuple[int, str, List[Tuple[str, Dict[str, Any], float, str]]]:
        query_text = route.subquery.text or route.subquery.to_serialized_query()
        clean_query = _clean_tsquery_term(query_text)
        if not clean_query:
            return route.subquery_index, query_text, []
        rows = await self.pgvector_store.keyword_search_async(
            collection_names=[scope.index_id for scope in route.collections],
            query_text=clean_query,
            k=top_k,
            company_name=(
                route.subquery.company.strip() if route.subquery.company not in ("", "?") else None
            ),
            sheet_name=(route.subquery.sheet if route.subquery.sheet not in ("", "?") else None),
        )
        return route.subquery_index, query_text, rows

    @staticmethod
    def _output(
        plan: RetrievalPlanDTO,
        cfg: PostgresNativeKeywordRetrieverConfigDTO,
        search_results: List[Tuple[int, str, List[Tuple[str, Dict[str, Any], float, str]]]],
    ) -> Dict[str, Any]:
        hits_by_subquery: Dict[int, List[Tuple[float, str, Dict[str, Any], str, str]]] = {}
        for subquery_index, query_text, rows in search_results:
            route_hits = hits_by_subquery.setdefault(subquery_index, [])
            for document, metadata, score, index_id in rows:
                route_hits.append(
                    (
                        score if score > 0 else 0.05,
                        index_id,
                        metadata,
                        document,
                        query_text,
                    )
                )

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
            "document_context": document_context_for_plan(plan).model_dump(mode="json"),
            "items": ranked_items,
        }

    def execute(
        self,
        input_data: PostgresNativeKeywordRetrieverInputDTO,
        config: Optional[PostgresNativeKeywordRetrieverConfigDTO] = None,
    ) -> Dict[str, Any]:
        cfg = config or PostgresNativeKeywordRetrieverConfigDTO()
        plan = input_data.retrieval_plan
        if not plan.routes:
            return {
                "query_context": plan.query_context.model_dump(mode="json"),
                "document_context": document_context_for_plan(plan).model_dump(mode="json"),
                "items": [],
            }
        return self._output(
            plan,
            cfg,
            [self._search_one(route, cfg.top_k) for route in plan.routes],
        )

    async def execute_async(
        self,
        input_data: PostgresNativeKeywordRetrieverInputDTO,
        config: Optional[PostgresNativeKeywordRetrieverConfigDTO] = None,
    ) -> Dict[str, Any]:
        cfg = config or PostgresNativeKeywordRetrieverConfigDTO()
        plan = input_data.retrieval_plan
        if not plan.routes:
            return {
                "query_context": plan.query_context.model_dump(mode="json"),
                "document_context": document_context_for_plan(plan).model_dump(mode="json"),
                "items": [],
            }
        tasks: List[
            asyncio.Task[
                Tuple[
                    int,
                    str,
                    List[Tuple[str, Dict[str, Any], float, str]],
                ]
            ]
        ] = []
        async with asyncio.TaskGroup() as task_group:
            tasks.extend(
                (
                    task_group.create_task(
                        self._search_one_async(route, cfg.top_k),
                        name=f"keyword-search:{route.subquery_index}",
                    )
                    for route in plan.routes
                )
            )
        return self._output(plan, cfg, [task.result() for task in tasks])


__all__ = [
    "PostgresNativeKeywordRetrieverConfigDTO",
    "PostgresNativeKeywordRetrieverInputDTO",
    "PostgresNativeKeywordRetrieverModule",
    "_clean_tsquery_term",
    "_escape_like_term",
]
