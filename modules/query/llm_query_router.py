"""Map every decomposed subquery to concrete PostgreSQL data scopes."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from modules.common.base_llm import (
    BaseLLMModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleDTO,
    ModuleExecutionError,
    ModuleInputDTO,
    QueryContextDTO,
)
from modules.common.base_module import DocumentContextDTO
from modules.common.config import DEFAULT_ROUTER_MODEL
from modules.query.decomposer import SubqueriesDTO, SubqueryItem
from modules.storage.pgvector_data_scope import DataScopeCatalogDTO, DataScopeDTO

ROUTER_SYSTEM_PROMPT = """You are a PostgreSQL retrieval-scope router.
Map every atomic subquery to the smallest set of concrete collection IDs that
contains the required company and sheet data.

Rules:
1. Return exactly one route for every zero-based subquery_index.
2. Select only index_id values present in the supplied data-scope catalog.
3. Prefer exact company and sheet matches; file names are supporting evidence.
4. A subquery may use multiple collections only when the answer truly spans them.
5. Never invent collection IDs and never route a query to every collection as a fallback.
"""


class RouteSelectionDTO(BaseModel):
    subquery_index: int = Field(ge=0)
    index_ids: List[str] = Field(min_length=1)
    reason: Optional[str] = None


class LlmRouterResponse(BaseModel):
    routes: List[RouteSelectionDTO] = Field(default_factory=list)


class RoutedSubqueryDTO(ModuleDTO):
    """One atomic query paired with the exact collections it may search."""

    subquery_index: int = Field(ge=0)
    subquery: SubqueryItem
    collections: List[DataScopeDTO] = Field(min_length=1)
    reason: Optional[str] = None


class RetrievalPlanDTO(ModuleDTO):
    """Canonical downstream contract for scoped hybrid retrieval."""

    query_context: QueryContextDTO
    routes: List[RoutedSubqueryDTO] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)

    @property
    def selected_index_ids(self) -> List[str]:
        return list(
            dict.fromkeys(
                scope.index_id
                for route in self.routes
                for scope in route.collections
            )
        )


def document_context_for_plan(plan: RetrievalPlanDTO) -> DocumentContextDTO:
    """Build one deterministic multi-collection lineage projection."""
    collections = list(
        {
            scope.index_id: scope
            for route in plan.routes
            for scope in route.collections
        }.values()
    )
    if not collections:
        return DocumentContextDTO(
            file_name="no-routed-document",
            workbook_hash="no-routed-workbook",
            index_id=None,
        )
    company_names = list(
        dict.fromkeys(scope.company_name for scope in collections if scope.company_name)
    )
    sheet_names = list(
        dict.fromkeys(
            sheet for scope in collections for sheet in scope.sheet_names
        )
    )
    return DocumentContextDTO(
        file_name=", ".join(scope.file_name for scope in collections),
        workbook_hash=",".join(scope.workbook_hash for scope in collections),
        index_id=",".join(scope.index_id for scope in collections),
        company_name=company_names[0] if len(company_names) == 1 else None,
        sheet_names=sheet_names or None,
    )


class LlmQueryRouterInputDTO(ModuleInputDTO):
    query_input: SubqueriesDTO
    scope_catalog: DataScopeCatalogDTO


class LlmQueryRouterConfigDTO(ModuleConfigDTO):
    model: str = Field(default=DEFAULT_ROUTER_MODEL)
    max_collections_per_subquery: int = Field(default=3, ge=1, le=10)


LlmQueryRouterOutputDTO = RetrievalPlanDTO


class LlmQueryRouterModule(BaseLLMModule):
    """Builds the collection-aware retrieval plan; no manual selection exists."""

    definition = ModuleDefinition(
        type="llm_query_router",
        label="LLM Query Router",
        category="Logic",
        description=(
            "분해된 각 서브쿼리를 DB catalog의 concrete collection에 자동 대응시킵니다."
        ),
        inputs=["query_input", "scope_catalog"],
        outputs=["retrieval_plan"],
        config_fields=["model", "max_collections_per_subquery"],
        raw_output=True,
        version="7",
    )
    input_model = LlmQueryRouterInputDTO
    config_model = LlmQueryRouterConfigDTO
    output_model = RetrievalPlanDTO

    def __init__(self, completion_client: Any) -> None:
        super().__init__(completion_client=completion_client)

    def execute(
        self,
        input_data: LlmQueryRouterInputDTO,
        config: Optional[LlmQueryRouterConfigDTO] = None,
    ) -> Dict[str, Any]:
        cfg = config or LlmQueryRouterConfigDTO()
        subqueries = input_data.query_input.items
        catalog = input_data.scope_catalog.collections
        if not subqueries:
            return {
                "query_context": input_data.query_input.query_context.model_dump(
                    mode="json"
                ),
                "routes": [],
                "metrics": {"kind": "llm_collection_router", "model": cfg.model},
            }
        if not catalog:
            raise ModuleExecutionError("라우팅할 PostgreSQL data scope가 없습니다")

        catalog_payload = [
            {
                "index_id": scope.index_id,
                "file_name": scope.file_name,
                "company_name": scope.company_name,
                "sheet_names": scope.sheet_names,
                "model": scope.model,
                "dimension": scope.dimension,
            }
            for scope in catalog
        ]
        subquery_payload = [
            {
                "subquery_index": index,
                **item.model_dump(mode="json"),
            }
            for index, item in enumerate(subqueries)
        ]
        prompt = json.dumps(
            {
                "question": input_data.query_input.query_context.question_text,
                "subqueries": subquery_payload,
                "data_scope_catalog": catalog_payload,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        parsed, usage, cost_usd, latency_seconds = self.complete_structured(
            messages_or_prompt=prompt,
            response_model=LlmRouterResponse,
            model=cfg.model,
            system_prompt=ROUTER_SYSTEM_PROMPT,
        )

        catalog_by_id = {scope.index_id: scope for scope in catalog}
        selections: Dict[int, RouteSelectionDTO] = {}
        for selection in parsed.routes:
            if selection.subquery_index >= len(subqueries):
                raise ModuleExecutionError(
                    f"Router가 존재하지 않는 subquery_index를 반환했습니다: "
                    f"{selection.subquery_index}"
                )
            if selection.subquery_index in selections:
                raise ModuleExecutionError(
                    f"Router가 subquery_index를 중복 반환했습니다: "
                    f"{selection.subquery_index}"
                )
            unique_ids = list(dict.fromkeys(selection.index_ids))
            unknown = [index_id for index_id in unique_ids if index_id not in catalog_by_id]
            if unknown:
                raise ModuleExecutionError(
                    "Router가 catalog에 없는 collection을 선택했습니다: "
                    + ", ".join(unknown)
                )
            if len(unique_ids) > cfg.max_collections_per_subquery:
                raise ModuleExecutionError(
                    f"서브쿼리당 collection 선택 한도는 "
                    f"{cfg.max_collections_per_subquery}개입니다"
                )
            selections[selection.subquery_index] = selection.model_copy(
                update={"index_ids": unique_ids}
            )

        missing = [index for index in range(len(subqueries)) if index not in selections]
        if missing:
            raise ModuleExecutionError(
                "Router가 collection을 지정하지 않은 서브쿼리가 있습니다: "
                + ", ".join(str(index) for index in missing)
            )

        routes = []
        for index, subquery in enumerate(subqueries):
            selection = selections[index]
            routes.append(
                RoutedSubqueryDTO(
                    subquery_index=index,
                    subquery=subquery,
                    collections=[catalog_by_id[index_id] for index_id in selection.index_ids],
                    reason=selection.reason,
                ).model_dump(mode="json")
            )
        return {
            "query_context": input_data.query_input.query_context.model_dump(mode="json"),
            "routes": routes,
            "metrics": {
                "kind": "llm_collection_router",
                "model": cfg.model,
                "latency_seconds": round(latency_seconds, 3),
                "api_usage": usage or {},
                "estimated_cost_usd": round(cost_usd, 8),
                "catalog_size": len(catalog),
                "route_count": len(routes),
            },
        }


__all__ = [
    "LlmQueryRouterConfigDTO",
    "LlmQueryRouterInputDTO",
    "LlmQueryRouterModule",
    "LlmQueryRouterOutputDTO",
    "LlmRouterResponse",
    "RetrievalPlanDTO",
    "RouteSelectionDTO",
    "RoutedSubqueryDTO",
    "document_context_for_plan",
]
