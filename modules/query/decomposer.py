"""Decompose a question into catalog-scoped atomic spreadsheet queries."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from modules.common.base_llm import (
    ApiUsageDTO,
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
10. For forward estimates, forecasts, outlooks, or future margin/EPS questions,
    prefer the exact Key_Stats sheet when that sheet exists in the selected
    company's catalog. Historical actual statements remain on their statement
    sheets unless the question explicitly asks for a Key Stats value.
11. Emit one atomic item for every operand needed by a comparison, trend,
    accounting identity, ratio, or derived calculation. Select only the minimum
    exact sheets required by those operands; do not add a merely related sheet.
12. Generic group phrases such as "the three companies" are not company names.
    Do not guess which catalog companies they mean when the current question
    does not name the members explicitly.
13. unresolved_companies may contain only literal company identities named in
    the current question. Never place a metric, account label, transaction,
    period, or generic group phrase in unresolved_companies.
14. Preserve the distinction between workbook metrics. Explicit 총매출 or
    Total Revenue means Total Revenue. Bare 매출 or 매출액 means Revenue unless
    the user explicitly asks for the consolidated total.
15. Preserve explicit source wording. 현금흐름표/Cash Flow Statement,
    손익계산서/Income Statement, 재무상태표/Balance Sheet, and Key Stats in the
    question are hard sheet constraints, not suggestions. Distinguish
    총부채/Total Liabilities from 총차입금/Total Debt.
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
    def _canonical_row_header(cls, question: str, requested_row_header: str) -> str:
        """Preserve explicit metric distinctions that models often collapse.

        Spreadsheet workbooks commonly contain both ``Revenue`` and
        ``Total Revenue``. Bare ``매출``/``매출액`` must not be silently widened
        because the workbook defines them as different FEATUREs. The same is
        true for accounting liabilities versus interest-bearing debt. Repairs
        fire only when the original question states the exact distinction.
        """

        normalized_row = cls._normalize_reference(requested_row_header)
        normalized_question = cls._normalize_reference(question)
        if normalized_row == "revenue":
            asks_for_total_revenue = any(
                token in normalized_question for token in ("총매출", "totalrevenue")
            )
            qualified_revenue = any(
                token in normalized_question
                for token in (
                    "부문",
                    "세그먼트",
                    "제품",
                    "서비스",
                    "구독",
                    "광고",
                    "segment",
                    "product",
                    "service",
                    "subscription",
                    "advertising",
                )
            )
            return (
                "Total Revenue"
                if asks_for_total_revenue and not qualified_revenue
                else requested_row_header
            )

        debt_aliases = {"debt", "totaldebt", "totalliabilities", "liabilities"}
        if normalized_row in debt_aliases:
            if any(
                token in normalized_question
                for token in ("총부채", "부채총계", "totalliabilities")
            ):
                return "Total Liabilities"
            if any(
                token in normalized_question
                for token in ("총차입금", "차입금전부", "totaldebt")
            ):
                return "Total Debt"
        return requested_row_header

    @classmethod
    def _explicit_sheet_from_question(
        cls,
        question: str,
        scopes: List[DataScopeDTO],
    ) -> str:
        """Resolve only a sheet name stated explicitly by the user."""

        normalized_question = cls._normalize_reference(question)
        hints = (
            (("현금흐름표", "cashflowstatement", "cashflow"), "Cash_Flow"),
            (("손익계산서", "incomestatement"), "Income_Statement"),
            (("재무상태표", "대차대조표", "balancesheet"), "Balance_Sheet"),
            (("keystats", "핵심재무지표"), "Key_Stats"),
        )
        matches = [
            canonical
            for tokens, canonical in hints
            if any(token in normalized_question for token in tokens)
        ]
        if len(matches) != 1:
            return UNKNOWN_FIELD
        return cls._canonical_sheet(matches[0], scopes)

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

        companies = {cls._normalize_reference(scope.company_name) for scope in partial_matches}
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
            "Decomposer가 catalog에 없는 collection을 반환했습니다: " + ", ".join(unknown_ids)
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
                "external_context_sources": (input_data.query_context.external_context_sources),
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

    @staticmethod
    def _external_companies(
        parsed: DecomposedSubqueriesResponse,
        external_sources: List[str],
    ) -> List[str]:
        companies = list(dict.fromkeys(parsed.external_context_companies))
        if not external_sources:
            return companies
        # Older or less capable models can still place attachment-owned names
        # in unresolved_companies. Attachment binding is the only condition
        # that permits those names to remain outside the pgvector catalog.
        return list(dict.fromkeys([*companies, *parsed.unresolved_companies]))

    @classmethod
    def _selection_scopes(
        cls,
        selection: ScopedSubquerySelection,
        catalog_by_id: Dict[str, DataScopeDTO],
        all_scopes: List[DataScopeDTO],
    ) -> tuple[List[DataScopeDTO], bool]:
        requested_ids = list(dict.fromkeys(index_id.strip() for index_id in selection.index_ids))
        company_scopes = cls._scopes_for_company(selection.company, all_scopes)
        nonempty_unknown_ids = [
            index_id for index_id in requested_ids if index_id and index_id not in catalog_by_id
        ]
        if "" in requested_ids and company_scopes and not nonempty_unknown_ids:
            return company_scopes, True
        known_ids = [index_id for index_id in requested_ids if index_id in catalog_by_id]
        if nonempty_unknown_ids and not known_ids and company_scopes:
            # The model occasionally copies or concatenates an index id even
            # though it selected an exact catalog company. Repairing *all*
            # unknown ids to that company's server-owned scopes cannot cross a
            # company boundary. Mixed known/unknown selections still fail
            # closed in ``_resolve_index_ids`` below.
            return company_scopes, True
        resolved, repaired = cls._resolve_index_ids(requested_ids, catalog_by_id)
        return [catalog_by_id[index_id] for index_id in resolved], repaired

    @classmethod
    def _truly_unresolved_companies(
        cls,
        parsed: DecomposedSubqueriesResponse,
        catalog: List[DataScopeDTO],
    ) -> List[str]:
        """Discard model-side false negatives that the server resolves exactly."""

        return [
            company
            for company in dict.fromkeys(parsed.unresolved_companies)
            if not cls._scopes_for_company(company, catalog)
        ]

    @staticmethod
    def _merge_usage(first: ApiUsageDTO, second: ApiUsageDTO) -> ApiUsageDTO:
        return ApiUsageDTO(
            prompt_tokens=(first.prompt_tokens or 0) + (second.prompt_tokens or 0),
            completion_tokens=(first.completion_tokens or 0)
            + (second.completion_tokens or 0),
            cached_tokens=(first.cached_tokens or 0) + (second.cached_tokens or 0),
            reasoning_tokens=(first.reasoning_tokens or 0)
            + (second.reasoning_tokens or 0),
            total_tokens=(first.total_tokens or 0) + (second.total_tokens or 0),
        )

    @classmethod
    def _needs_empty_plan_retry(
        cls,
        input_data: DecomposerInputDTO,
        parsed: DecomposedSubqueriesResponse,
    ) -> bool:
        return (
            not parsed.items
            and not input_data.query_context.external_context_sources
            and not cls._truly_unresolved_companies(
                parsed,
                input_data.scope_catalog.collections,
            )
        )

    @staticmethod
    def _retry_prompt(prompt: str) -> str:
        return (
            prompt
            + "\n\nYour previous response produced no usable catalog route even though "
            "the question can be resolved against the supplied catalog. Re-read the "
            "original question, select only exact index_id values from the catalog, "
            "and return every required atomic item. Do not report a catalog company "
            "as unresolved."
        )

    @classmethod
    def _routed_subquery(
        cls,
        selection: ScopedSubquerySelection,
        scopes: List[DataScopeDTO],
        route_index: int,
        question: str,
        allow_question_sheet_override: bool = True,
    ) -> RoutedSubqueryDTO:
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
                "하나의 서브쿼리가 여러 기업 collection을 선택했습니다: " + ", ".join(company_names)
            )
        explicit_sheet = (
            cls._explicit_sheet_from_question(question, scopes)
            if allow_question_sheet_override
            else UNKNOWN_FIELD
        )
        subquery = SubqueryItem(
            company=company_names[0] if company_names else selection.company,
            sheet=(
                explicit_sheet
                if explicit_sheet != UNKNOWN_FIELD
                else cls._canonical_sheet(selection.sheet, scopes)
            ),
            row_header=cls._canonical_row_header(question, selection.row_header),
            column_header=selection.column_header,
            cell_value=selection.cell_value,
        )
        return RoutedSubqueryDTO(
            subquery_index=route_index,
            subquery=subquery,
            collections=scopes,
            reason=selection.reason,
        )

    @classmethod
    def _output(
        cls,
        input_data: DecomposerInputDTO,
        cfg: DecomposerConfigDTO,
        parsed: DecomposedSubqueriesResponse,
        usage: Any,
        cost_usd: float,
        latency_seconds: float,
        decomposition_attempts: int = 1,
    ) -> Dict[str, Any]:
        external_sources = input_data.query_context.external_context_sources
        unresolved_companies = cls._truly_unresolved_companies(
            parsed,
            input_data.scope_catalog.collections,
        )
        if unresolved_companies and not external_sources:
            available = ", ".join(
                scope.company_name or scope.file_name
                for scope in input_data.scope_catalog.collections
            )
            raise ModuleExecutionError(
                "검색 catalog에서 기업을 찾지 못했습니다: "
                + ", ".join(unresolved_companies)
                + f". 현재 검색 가능 기업: {available}"
            )

        external_companies = cls._external_companies(parsed, external_sources)

        catalog_by_id = {scope.index_id: scope for scope in input_data.scope_catalog.collections}
        routes: List[Dict[str, Any]] = []
        seen: set[tuple[str, tuple[str, ...]]] = set()
        repaired_scope_count = 0
        for selection in parsed.items:
            company_scopes = cls._scopes_for_company(
                selection.company,
                input_data.scope_catalog.collections,
            )
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

            scopes, repaired = cls._selection_scopes(
                selection,
                catalog_by_id,
                input_data.scope_catalog.collections,
            )
            repaired_scope_count += int(repaired)
            selected_scopes = scopes[: cfg.max_collections_per_subquery]
            route = cls._routed_subquery(
                selection,
                selected_scopes,
                len(routes),
                input_data.query_context.question_text,
                allow_question_sheet_override=len(parsed.items) == 1,
            )
            identity = (
                route.subquery.to_serialized_query(),
                tuple(scope.index_id for scope in selected_scopes),
            )
            if identity in seen:
                continue
            seen.add(identity)
            routes.append(route.model_dump(mode="json"))

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
                "decomposition_attempts": decomposition_attempts,
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
        decomposition_attempts = 1
        if self._needs_empty_plan_retry(input_data, parsed):
            retry_parsed, retry_usage, retry_cost, retry_latency = self.complete_structured(
                messages_or_prompt=self._retry_prompt(prompt),
                response_model=DecomposedSubqueriesResponse,
                model=cfg.model,
                system_prompt=cfg.system_prompt or LUNA_SYSTEM_PROMPT,
            )
            parsed = retry_parsed
            usage = self._merge_usage(usage, retry_usage)
            cost_usd += retry_cost
            latency_seconds += retry_latency
            decomposition_attempts = 2
        return self._output(
            input_data,
            cfg,
            parsed,
            usage,
            cost_usd,
            latency_seconds,
            decomposition_attempts,
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
        decomposition_attempts = 1
        if self._needs_empty_plan_retry(input_data, parsed):
            retry_parsed, retry_usage, retry_cost, retry_latency = (
                await self.complete_structured_async(
                    messages_or_prompt=self._retry_prompt(prompt),
                    response_model=DecomposedSubqueriesResponse,
                    model=cfg.model,
                    system_prompt=cfg.system_prompt or LUNA_SYSTEM_PROMPT,
                )
            )
            parsed = retry_parsed
            usage = self._merge_usage(usage, retry_usage)
            cost_usd += retry_cost
            latency_seconds += retry_latency
            decomposition_attempts = 2
        return self._output(
            input_data,
            cfg,
            parsed,
            usage,
            cost_usd,
            latency_seconds,
            decomposition_attempts,
        )


__all__ = [
    "DecomposedSubqueriesResponse",
    "DecomposerConfigDTO",
    "DecomposerInputDTO",
    "DecomposerModule",
    "ScopedSubquerySelection",
]
