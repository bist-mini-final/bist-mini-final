"""Decompose a question into catalog-scoped atomic spreadsheet queries."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from modules.common.base_llm import (
    BaseLLMModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleExecutionError,
    ModuleInputDTO,
    QueryContextDTO,
)
from modules.common.config import DEFAULT_LLM_MODEL
from modules.query.contracts import (
    UNKNOWN_FIELD,
    RetrievalPlanDTO,
    RoutedSubqueryDTO,
    SubqueryItem,
)
from modules.storage.pgvector_data_scope import DataScopeCatalogDTO, DataScopeDTO

LUNA_SYSTEM_PROMPT = """You are a catalog-scoped Spreadsheet Query Decomposition Assistant.
Decompose the user's question into every atomic cell-search subquery required to
answer it. Each stored vector represents one spreadsheet cell.

Rules:
1. Create a separate subquery for every company, metric, and period.
2. Select only index_id values present in data_scope_catalog. Never invent an ID.
3. Resolve company aliases using company_name and ticker from the catalog. Treat
   spacing, punctuation, and casing differences as harmless aliases.
4. Use the exact catalog company_name in each item. Use the exact sheet name when
   it can be inferred from the catalog; otherwise use '?'.
5. Normalize row headers with useful canonical financial terminology and normalize
   periods such as YYYY, FYYYYY, quarter, LTM, and TTM.
6. Use '?' only when a field truly cannot be inferred. Cell Value is normally '?'
   because retrieval is expected to discover the value.
7. If a company in the question does not match the catalog, do not substitute a
   similar company. When external_context_sources is empty, add the unmatched
   name to unresolved_companies. When external_context_sources is not empty,
   treat the unmatched company as attachment-owned: add it to
   external_context_companies and continue decomposing every catalog company.
8. A subquery may select multiple collections only when they belong to the same
   requested company and the answer genuinely spans those workbooks.
9. Never create a retrieval item or index_id for an attachment-owned company.
"""


class ScopedSubquerySelection(BaseModel):
    """LLM-produced atomic query plus catalog identifiers."""

    company: str = Field(default=UNKNOWN_FIELD)
    sheet: str = Field(default=UNKNOWN_FIELD)
    row_header: str = Field(default=UNKNOWN_FIELD)
    column_header: str = Field(default=UNKNOWN_FIELD)
    cell_value: str = Field(default=UNKNOWN_FIELD)
    index_ids: List[str] = Field(min_length=1)
    reason: Optional[str] = None


class DecomposedSubqueriesResponse(BaseModel):
    items: List[ScopedSubquerySelection] = Field(default_factory=list)
    unresolved_companies: List[str] = Field(default_factory=list)
    external_context_companies: List[str] = Field(default_factory=list)


class DecomposerInputDTO(ModuleInputDTO):
    query_context: QueryContextDTO
    scope_catalog: DataScopeCatalogDTO


class DecomposerConfigDTO(ModuleConfigDTO):
    model: str = Field(default=DEFAULT_LLM_MODEL)
    max_collections_per_subquery: int = Field(default=3, ge=1, le=10)
    system_prompt: Optional[str] = None
    user_prompt_template: Optional[str] = None


class DecomposerModule(BaseLLMModule):
    """Creates an atomic, catalog-validated retrieval plan in one LLM call."""

    definition = ModuleDefinition(
        type="decomposer",
        label="Scope-aware Query Decomposer",
        category="Logic",
        description=(
            "질문과 PostgreSQL collection catalog를 함께 받아 실제 기업·시트 범위에 "
            "고정된 원자 검색 계획을 생성합니다."
        ),
        inputs=["query_context", "scope_catalog"],
        outputs=["retrieval_plan"],
        config_fields=[
            "model",
            "max_collections_per_subquery",
            "system_prompt",
            "user_prompt_template",
        ],
        raw_output=True,
        version="11",
    )
    input_model = DecomposerInputDTO
    config_model = DecomposerConfigDTO
    output_model = RetrievalPlanDTO

    def __init__(self, completion_client: Any) -> None:
        super().__init__(completion_client=completion_client)

    @staticmethod
    def _normalize_reference(value: str) -> str:
        return re.sub(r"[^0-9a-z가-힣]+", "", value.casefold())

    @classmethod
    def _canonical_sheet(
        cls,
        requested_sheet: str,
        scopes: List[DataScopeDTO],
    ) -> str:
        normalized = cls._normalize_reference(requested_sheet)
        if not normalized or requested_sheet == UNKNOWN_FIELD:
            return UNKNOWN_FIELD
        for scope in scopes:
            for sheet_name in scope.sheet_names:
                if cls._normalize_reference(sheet_name) == normalized:
                    return sheet_name
        return UNKNOWN_FIELD

    @classmethod
    def _company_matches_scopes(
        cls,
        requested_company: str,
        scopes: List[DataScopeDTO],
    ) -> bool:
        normalized = cls._normalize_reference(requested_company)
        if not normalized or requested_company == UNKNOWN_FIELD:
            return True
        aliases: set[str] = set()
        for scope in scopes:
            base_name = scope.company_name.split("(", 1)[0].strip()
            aliases.update(
                cls._normalize_reference(alias)
                for alias in (scope.company_name, base_name, scope.ticker)
                if alias.strip()
            )
        return normalized in aliases

    @classmethod
    def _scopes_for_company(
        cls,
        requested_company: str,
        scopes: List[DataScopeDTO],
    ) -> List[DataScopeDTO]:
        """Resolve a company name to catalog scopes without crossing companies."""

        normalized = cls._normalize_reference(requested_company)
        if not normalized or requested_company == UNKNOWN_FIELD:
            return []

        exact_matches = [
            scope for scope in scopes if cls._company_matches_scopes(requested_company, [scope])
        ]
        if exact_matches:
            return exact_matches

        # A user or model can omit a legal-name suffix (for example, "Nexora"
        # versus "Nexora Labs"). Prefix repair is accepted only when every
        # matched scope belongs to one canonical company, so it cannot broaden
        # retrieval to a similarly named company.
        partial_matches: List[DataScopeDTO] = []
        for scope in scopes:
            base_name = scope.company_name.split("(", 1)[0].strip()
            aliases = {
                cls._normalize_reference(alias)
                for alias in (scope.company_name, base_name, scope.ticker)
                if alias.strip()
            }
            if any(
                len(alias) >= 4
                and len(normalized) >= 4
                and (alias.startswith(normalized) or normalized.startswith(alias))
                for alias in aliases
            ):
                partial_matches.append(scope)

        companies = {
            cls._normalize_reference(scope.company_name) for scope in partial_matches
        }
        return partial_matches if len(companies) == 1 else []

    @staticmethod
    def _resolve_index_ids(
        requested_ids: List[str],
        catalog_by_id: Dict[str, DataScopeDTO],
    ) -> tuple[List[str], bool]:
        unique_ids = list(dict.fromkeys(requested_ids))
        unknown_ids = [index_id for index_id in unique_ids if index_id not in catalog_by_id]
        if not unknown_ids:
            return unique_ids, False
        if len(catalog_by_id) == 1:
            # A server-owned single-source workflow has already fixed the data
            # lineage. Repairing an LLM typo to that sole scope cannot broaden
            # access; multi-scope workflows still fail closed below.
            return [next(iter(catalog_by_id))], True
        raise ModuleExecutionError(
            "Decomposer가 catalog에 없는 collection을 반환했습니다: "
            + ", ".join(unknown_ids)
        )

    @staticmethod
    def _prompt(input_data: DecomposerInputDTO) -> str:
        catalog_payload = [
            {
                "index_id": scope.index_id,
                "file_name": scope.file_name,
                "company_name": scope.company_name,
                "ticker": scope.ticker,
                "sheet_names": scope.sheet_names,
                "model": scope.model,
                "dimension": scope.dimension,
            }
            for scope in input_data.scope_catalog.collections
        ]
        return json.dumps(
            {
                "question": input_data.query_context.question_text,
                "data_scope_catalog": catalog_payload,
                "external_context_sources": (
                    input_data.query_context.external_context_sources
                ),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

    @classmethod
    def _user_prompt(
        cls,
        input_data: DecomposerInputDTO,
        cfg: DecomposerConfigDTO,
    ) -> str:
        catalog_prompt = cls._prompt(input_data)
        if not cfg.user_prompt_template:
            return catalog_prompt
        prompt = cfg.user_prompt_template.format(
            question=input_data.query_context.question_text,
            catalog=catalog_prompt,
        )
        if "{catalog}" not in cfg.user_prompt_template:
            prompt += "\n\nCatalog context:\n" + catalog_prompt
        return prompt

    @classmethod
    def _output(
        cls,
        input_data: DecomposerInputDTO,
        cfg: DecomposerConfigDTO,
        parsed: DecomposedSubqueriesResponse,
        usage: Any,
        cost_usd: float,
        latency_seconds: float,
    ) -> Dict[str, Any]:
        external_sources = input_data.query_context.external_context_sources
        if parsed.unresolved_companies and not external_sources:
            available = ", ".join(
                scope.company_name or scope.file_name
                for scope in input_data.scope_catalog.collections
            )
            raise ModuleExecutionError(
                "검색 catalog에서 기업을 찾지 못했습니다: "
                + ", ".join(parsed.unresolved_companies)
                + f". 현재 검색 가능 기업: {available}"
            )

        external_companies = list(dict.fromkeys(parsed.external_context_companies))
        if external_sources:
            # Older or less capable models can still place attachment-owned
            # names in unresolved_companies. The server accepts those names as
            # external only for an explicitly attachment-bound run; it never
            # grants them a collection or broadens pgvector access.
            external_companies = list(
                dict.fromkeys([*external_companies, *parsed.unresolved_companies])
            )

        catalog_by_id = {
            scope.index_id: scope for scope in input_data.scope_catalog.collections
        }
        routes: List[Dict[str, Any]] = []
        seen: set[tuple[str, tuple[str, ...]]] = set()
        repaired_scope_count = 0
        for selection in parsed.items:
            requested_ids = list(dict.fromkeys(index_id.strip() for index_id in selection.index_ids))
            company_scopes = cls._scopes_for_company(
                selection.company,
                input_data.scope_catalog.collections,
            )
            nonempty_unknown_ids = [
                index_id
                for index_id in requested_ids
                if index_id and index_id not in catalog_by_id
            ]

            if not company_scopes and external_sources:
                # Attachment-owned companies never receive a pgvector scope.
                # Models occasionally emit a placeholder/empty index despite
                # the prompt; discard that route and keep it in external
                # context instead of widening catalog access.
                if selection.company != UNKNOWN_FIELD:
                    external_companies = list(
                        dict.fromkeys([*external_companies, selection.company])
                    )
                continue

            if "" in requested_ids and company_scopes and not nonempty_unknown_ids:
                unique_ids = list(dict.fromkeys(scope.index_id for scope in company_scopes))
                repaired = True
            else:
                unique_ids, repaired = cls._resolve_index_ids(
                    requested_ids,
                    catalog_by_id,
                )
            repaired_scope_count += int(repaired)
            selected_ids = unique_ids[: cfg.max_collections_per_subquery]
            scopes = [catalog_by_id[index_id] for index_id in selected_ids]
            if not cls._company_matches_scopes(selection.company, scopes):
                raise ModuleExecutionError(
                    "Decomposer의 기업명과 선택 collection의 catalog 기업이 일치하지 않습니다: "
                    f"{selection.company}"
                )
            company_names = list(
                dict.fromkeys(scope.company_name for scope in scopes if scope.company_name)
            )
            if len(company_names) > 1:
                raise ModuleExecutionError(
                    "하나의 서브쿼리가 여러 기업 collection을 선택했습니다: "
                    + ", ".join(company_names)
                )
            subquery = SubqueryItem(
                company=company_names[0] if company_names else selection.company,
                sheet=cls._canonical_sheet(selection.sheet, scopes),
                row_header=selection.row_header,
                column_header=selection.column_header,
                cell_value=selection.cell_value,
            )
            serialized = subquery.to_serialized_query()
            identity = (serialized, tuple(selected_ids))
            if identity in seen:
                continue
            seen.add(identity)
            routes.append(
                RoutedSubqueryDTO(
                    subquery_index=len(routes),
                    subquery=subquery,
                    collections=scopes,
                    reason=selection.reason,
                ).model_dump(mode="json")
            )

        if not routes:
            raise ModuleExecutionError(
                "질문을 검색 가능한 catalog 범위의 서브쿼리로 분해하지 못했습니다"
            )
        return {
            "query_context": input_data.query_context.model_dump(mode="json"),
            "routes": routes,
            "metrics": {
                "kind": "scope_aware_decomposer",
                "model": cfg.model,
                "latency_seconds": round(latency_seconds, 3),
                "api_usage": usage or {},
                "estimated_cost_usd": round(cost_usd, 8),
                "catalog_size": len(catalog_by_id),
                "route_count": len(routes),
                "repaired_scope_count": repaired_scope_count,
                "external_context_sources": external_sources,
                "external_context_companies": external_companies,
            },
        }

    def execute(
        self,
        input_data: DecomposerInputDTO,
        config: Optional[DecomposerConfigDTO] = None,
    ) -> Dict[str, Any]:
        cfg = config or DecomposerConfigDTO()
        if not input_data.scope_catalog.collections:
            raise ModuleExecutionError("분해에 사용할 PostgreSQL data scope가 없습니다")
        prompt = self._user_prompt(input_data, cfg)
        parsed, usage, cost_usd, latency_seconds = self.complete_structured(
            messages_or_prompt=prompt,
            response_model=DecomposedSubqueriesResponse,
            model=cfg.model,
            system_prompt=cfg.system_prompt or LUNA_SYSTEM_PROMPT,
        )
        return self._output(
            input_data,
            cfg,
            parsed,
            usage,
            cost_usd,
            latency_seconds,
        )

    async def execute_async(
        self,
        input_data: DecomposerInputDTO,
        config: Optional[DecomposerConfigDTO] = None,
    ) -> Dict[str, Any]:
        cfg = config or DecomposerConfigDTO()
        if not input_data.scope_catalog.collections:
            raise ModuleExecutionError("분해에 사용할 PostgreSQL data scope가 없습니다")
        prompt = self._user_prompt(input_data, cfg)
        parsed, usage, cost_usd, latency_seconds = await self.complete_structured_async(
            messages_or_prompt=prompt,
            response_model=DecomposedSubqueriesResponse,
            model=cfg.model,
            system_prompt=cfg.system_prompt or LUNA_SYSTEM_PROMPT,
        )
        return self._output(
            input_data,
            cfg,
            parsed,
            usage,
            cost_usd,
            latency_seconds,
        )


__all__ = [
    "DecomposedSubqueriesResponse",
    "DecomposerConfigDTO",
    "DecomposerInputDTO",
    "DecomposerModule",
    "ScopedSubquerySelection",
]
