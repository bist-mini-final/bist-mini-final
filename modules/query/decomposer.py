from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Optional, Any, Dict, Iterable, List, Literal, Optional, Sequence, Tuple, cast

from pydantic import BaseModel, Field

from backend.providers.llm.chat_completion import ChatCompletionClient, ChatCompletionError, ChatCompletionResult
from backend.semantic_matching.plan_validation import validate_plan_reuse
from modules.common.base_module import (
    BaseModule,
    EmptyModuleConfigDTO,
    ModuleConfigDTO,
    ModuleConfigPreset,
    ModuleDefinition,
    ModuleDTO,
    ModuleExecutionError,
    ModuleInputDTO,
    QueryContextDTO,
)
from modules.common.config import DEFAULT_LLM_MODEL, DEFAULT_PLAN_REUSE_THRESHOLD
from modules.query.financial_thesaurus import format_thesaurus_prompt_guide
from modules.query.semantic_query_matcher import SemanticQueryMatchOutput


# ==============================================================================
# Subquery Formatting & Normalization Helpers
# ==============================================================================
UNKNOWN_FIELD = "?"

PERIOD_EQUIVALENT_GROUPS: Sequence[Sequence[str]] = (
    ("LTM", "FY0", "FY2025", "2025-12-31"),
    ("FY-1", "FY2024", "2024-12-31"),
    ("FY-2", "FY2023", "2023-12-31"),
    ("FY-3", "FY2022", "2022-12-31"),
    ("FY-4", "FY2021", "2021-12-31"),
    ("FY1", "FY2026", "2026-12-31"),
)

METRIC_EQUIVALENT_GROUPS: Sequence[Sequence[str]] = (
    (
        "TEV/EBITDA",
        "Enterprise Value/EBITDA",
        "Enterprise Value to EBITDA",
        "Enterprise Value to EBITDA Multiple",
    ),
    ("Total Enterprise Value", "Enterprise Value", "TEV"),
    ("Market Capitalization", "Market Cap", "Equity Market Value"),
    ("Net Income", "Net Income to Company"),
    ("Total Revenue", "Total Revenues", "Revenue", "Revenues", "Net Sales"),
    ("Operating Income", "EBIT", "Operating Profit"),
    ("Capital Expenditure", "CapEx", "Capital Expenditure (actual)"),
    (
        "Shares Outstanding",
        "Weighted Avg. Diluted Shares Out.",
        "Total Shares Out. on Filing Date",
    ),
    (
        "Cash and Short-Term Investments",
        "Total Cash & ST Investments",
        "Cash and Cash Equivalents",
        "Short-Term Investments",
    ),
    ("EBITDA Margin", "Margin %", "EBITDA Margin %"),
)


def serialize_structured_query(
    sheet: str = UNKNOWN_FIELD,
    row_header: str = UNKNOWN_FIELD,
    column_header: str = UNKNOWN_FIELD,
    cell_value: str = UNKNOWN_FIELD,
) -> str:
    return (
        f"Sheet: {sheet or UNKNOWN_FIELD} | "
        f"Row Header: {row_header or UNKNOWN_FIELD} | "
        f"Column Header: {column_header or UNKNOWN_FIELD} | "
        f"Cell Value: {cell_value or UNKNOWN_FIELD}"
    )


def normalize_structured_query(value: object) -> str:
    """Fix the field order and fill every missing field with `?`."""
    if not isinstance(value, str):
        raise ValueError("서브쿼리 항목은 문자열이어야 합니다")
    text = value.strip()
    fields = {}
    for part in text.split("|"):
        if ":" not in part:
            continue
        key, field_value = part.split(":", 1)
        fields[key.strip().lower()] = field_value.strip() or UNKNOWN_FIELD
    if not fields:
        raise ValueError("서브쿼리에 구조화 필드가 없습니다")

    sheet = fields.get("sheet", UNKNOWN_FIELD)
    sheet_aliases = {
        "balance sheet": "Balance_Sheet",
        "balance_sheet": "Balance_Sheet",
        "income statement": "Income_Statement",
        "income_statement": "Income_Statement",
        "cash flow statement": "Cash_Flow",
        "cash flow": "Cash_Flow",
        "cash_flow": "Cash_Flow",
        "key stats": "Key_Stats",
        "key statistics": "Key_Stats",
        "key_stats": "Key_Stats",
    }
    raw_sheet = fields.get("sheet", UNKNOWN_FIELD) or UNKNOWN_FIELD
    sheet = sheet_aliases.get(raw_sheet.lower(), raw_sheet) or UNKNOWN_FIELD
    return serialize_structured_query(
        sheet=sheet,
        row_header=fields.get("row header", UNKNOWN_FIELD) or UNKNOWN_FIELD,
        column_header=fields.get("column header", UNKNOWN_FIELD) or UNKNOWN_FIELD,
        cell_value=fields.get("cell value", UNKNOWN_FIELD) or UNKNOWN_FIELD,
    )


def normalize_subqueries(values: Iterable[object]) -> List[str]:
    normalized: List[str] = []
    for value in values:
        if not str(value).strip():
            continue
        query = normalize_structured_query(value)
        if query not in normalized:
            normalized.append(query)
    return normalized


def _structured_fields(value: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for part in value.split("|"):
        key, separator, field_value = part.partition(":")
        if separator:
            fields[key.strip().lower()] = field_value.strip() or UNKNOWN_FIELD
    return fields


def _alias_pattern(alias: str) -> str:
    return rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])"


def _expand_metric_aliases(row_header: str) -> List[str]:
    variants = [row_header]
    for group in METRIC_EQUIVALENT_GROUPS:
        expanded: List[str] = []
        aliases = sorted(group, key=len, reverse=True)
        for variant in variants:
            matched_alias = next(
                (
                    alias
                    for alias in aliases
                    if re.search(_alias_pattern(alias), variant, flags=re.IGNORECASE)
                ),
                None,
            )
            replacements = group if matched_alias else (variant,)
            for replacement in replacements:
                candidate = (
                    re.sub(
                        _alias_pattern(matched_alias),
                        replacement,
                        variant,
                        count=1,
                        flags=re.IGNORECASE,
                    )
                    if matched_alias
                    else replacement
                )
                if candidate not in expanded:
                    expanded.append(candidate)
        variants = expanded
    return variants


def _expand_period_aliases(column_header: str) -> List[str]:
    normalized = column_header.strip()
    for group in PERIOD_EQUIVALENT_GROUPS:
        if any(normalized.casefold() == alias.casefold() for alias in group):
            return list(group)
    return [normalized]


def augment_subqueries(subqueries: Iterable[str]) -> List[str]:
    """Expand each atomic query into every known metric and period alias pair."""
    result: List[str] = []

    def append(query: str) -> None:
        normalized = normalize_structured_query(query)
        if normalized not in result:
            result.append(normalized)

    for subquery in subqueries:
        normalized = normalize_structured_query(subquery)
        fields = _structured_fields(normalized)
        row_header = re.sub(
            r"\b(Actual|Estimate|Forecast)\b",
            "",
            fields.get("row header", UNKNOWN_FIELD),
            flags=re.IGNORECASE,
        )
        row_header = re.sub(r"\s{2,}", " ", row_header).strip() or UNKNOWN_FIELD
        column_header = fields.get("column header", UNKNOWN_FIELD)

        for metric_variant in _expand_metric_aliases(row_header):
            for period_variant in _expand_period_aliases(column_header):
                append(
                    serialize_structured_query(
                        sheet=fields.get("sheet", UNKNOWN_FIELD),
                        row_header=metric_variant,
                        column_header=period_variant,
                        cell_value=fields.get("cell value", UNKNOWN_FIELD),
                    )
                )
    return result


# ==============================================================================
# Prompts & Presets
# ==============================================================================
LUNA_SYSTEM_PROMPT = """You are a Spreadsheet Query Decomposition Assistant for RAG retrieval over structured Excel workbooks.
Analyze the user's natural language question and return every useful atomic cell-search subquery. Retrieval coverage is prioritized over brevity.

Guidelines:
1. Header Concept Normalization & Synonyms:
   - Normalize question concepts into formal spreadsheet header terms (row headers and column headers).
   - For each target metric or line item, emit separate subqueries for its canonical name and established synonyms or abbreviations that could appear in spreadsheet headers.
   - Keep standard business and domain abbreviations (e.g., EBIT, EBITDA, CapEx, YoY, CAGR, Q1, Q2, etc.) while also generating expanded terms.

2. Date, Time, and Category Period Handling:
   - Recognize all chronological, fiscal, quarter, month, or version periods explicitly mentioned in or inferred from the user query.
   - For requested periods, emit corresponding header variants (e.g., specific dates, fiscal years like FY2024 / FY2023, quarters like 2024 Q3, or relative periods like LTM / YTD / FY-1).
   - Put only one specific period representation in each atomic subquery. Never combine alternatives into a single column header.

3. Atomic Single-Cell Subquery Principle (CRITICAL):
   - In our vector database, EACH VECTOR CORRESPONDS TO A SINGLE ATOMIC CELL (a specific metric/item in a specific column/period).
   - Generate the full cross-product of independently requested metrics, metric aliases, and period aliases.
   - DO NOT generate range expressions or concatenated strings (e.g., DO NOT output "2021 to 2024", "Metric A, Metric B").
   - FOR MULTI-PERIOD, CAGR, YoY, OR TREND QUERIES:
     - You MUST GENERATE INDIVIDUAL ATOMIC SUBQUERIES FOR EVERY SINGLE PERIOD AND METRIC IN THAT SCOPE!

4. Structured Output Format (CRITICAL):
   - Every subquery MUST use this exact four-field format:
     "Sheet: {sheet or ?} | Row Header: {row_header or ?} | Column Header: {column_header or ?} | Cell Value: {value or ?}"
   - Use `?` for every field that was not explicitly specified.
   - Do not omit a field. Do not add fields. Do not use `N/A`.
   - Example: "Sheet: ? | Row Header: Total Revenue | Column Header: 2024 | Cell Value: ?"
   - Output ONLY a valid JSON array of these strings without markdown fences or extra explanations.
"""

LUNA_USER_TEMPLATE = """User Query: "{question}"
JSON Output:"""

DECOMPOSER_SYSTEM_PROMPT = LUNA_SYSTEM_PROMPT
DECOMPOSER_USER_TEMPLATE = LUNA_USER_TEMPLATE

RDB_FINANCIAL_SYSTEM_PROMPT = """Decompose the user's query into atomic spreadsheet header searches.
Create separate subqueries for every metric synonym and every equivalent period representation.
Return only a JSON array where each item follows the exact format:
Sheet: ? | Row Header: {row_header or ?} | Column Header: {column_header or ?} | Cell Value: ?"""

SIMPLE_SYSTEM_PROMPT = """Extract each independently searchable table metric and period from the query.
Create separate atomic queries for each requested metric and period.
Return only a JSON array where each item follows the exact format:
Sheet: ? | Row Header: {row_header or ?} | Column Header: {column_header or ?} | Cell Value: ?"""


DECOMPOSER_PRESETS: Dict[str, Dict[str, str]] = {
    "luna_decomposer": {
        "label": "Luna 원자 셀 분해 (권장)",
        "system_prompt": LUNA_SYSTEM_PROMPT,
        "user_prompt_template": LUNA_USER_TEMPLATE,
    },
    "rdb_financial": {
        "label": "RDB 구조화 헤더 매처",
        "system_prompt": RDB_FINANCIAL_SYSTEM_PROMPT,
        "user_prompt_template": LUNA_USER_TEMPLATE,
    },
    "simple_decomposer": {
        "label": "단순 키워드 원자 분해",
        "system_prompt": SIMPLE_SYSTEM_PROMPT,
        "user_prompt_template": LUNA_USER_TEMPLATE,
    },
}


def decomposer_config_presets() -> List[Dict[str, Any]]:
    return [
        {
            "id": preset_id,
            "label": preset["label"],
            "values": {
                "preset": preset_id,
                "system_prompt": preset["system_prompt"],
                "user_prompt_template": preset["user_prompt_template"],
            },
        }
        for preset_id, preset in DECOMPOSER_PRESETS.items()
    ]


# ==============================================================================
# DTOs
# ==============================================================================
class DecomposerInputDTO(ModuleInputDTO):
    query_context: QueryContextDTO = Field(
        description="Query Input에서 전달된 질문 ID와 원문 질문",
    )


class DecomposerConfigDTO(ModuleConfigDTO):
    model: str = Field(
        default=DEFAULT_LLM_MODEL, description="질의 분해에 사용할 LLM ID"
    )
    preset: Literal[
        "luna_decomposer",
        "rdb_financial",
        "simple_decomposer",
    ] = Field(
        default="luna_decomposer",
        description="적용할 프롬프트 프리셋 ID",
    )
    system_prompt: str = Field(
        default=LUNA_SYSTEM_PROMPT,
        description="원자 단위 서브쿼리 생성 규칙을 정의하는 시스템 프롬프트",
    )
    user_prompt_template: str = Field(
        default=LUNA_USER_TEMPLATE,
        description="{question} 변수를 지원하는 사용자 프롬프트 템플릿",
    )


class DecomposerExecutionDTO(DecomposerInputDTO, DecomposerConfigDTO):
    """Internal union of the public input and module settings."""


class SubqueriesDTO(ModuleDTO):
    query_context: QueryContextDTO = Field(
        description="분해 대상이 된 원본 질문 메타데이터"
    )
    subqueries: List[str] = Field(
        description="구조화된 4필드 포맷의 서브쿼리 목록",
    )


# ==============================================================================
# Module Implementation
# ==============================================================================
class DecomposerModule(BaseModule):
    definition = ModuleDefinition(
        type="decomposer",
        label="LLM Query Decomposer",
        category="Logic",
        description="사용자 질문을 원자 단위 서브쿼리로 분해합니다.",
        inputs=["input"],
        outputs=["output"],
        config_fields=["model", "preset", "system_prompt", "user_prompt_template"],
        raw_output=True,
        version="6",
    )
    input_model = DecomposerInputDTO
    config_model = DecomposerConfigDTO
    execution_model = DecomposerExecutionDTO
    output_model = SubqueriesDTO

    def __init__(
        self,
        completion_client: Optional[ChatCompletionClient] = None,
    ) -> None:
        self.completion_client = completion_client or ChatCompletionClient()

    def execute(
        self,
        input_data: DecomposerInputDTO,
        config: Optional[DecomposerConfigDTO] = None,
    ) -> Dict[str, Any]:
        if config is None and isinstance(input_data, DecomposerExecutionDTO):
            config = input_data
        model_name = config.model if config else DEFAULT_LLM_MODEL
        sys_prompt = config.system_prompt if config else LUNA_SYSTEM_PROMPT
        user_tmpl = config.user_prompt_template if config else LUNA_USER_TEMPLATE

        prompt = user_tmpl.format(
            question=input_data.query_context.question_text,
        )
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": prompt},
        ]
        if hasattr(self.completion_client, "complete_with_metadata"):
            try:
                res = self.completion_client.complete_with_metadata(
                    model=model_name,
                    messages=messages,
                )
                text = res.content
                self.last_usage = res.usage
            except Exception:
                text = self.completion_client.complete(model_name, messages)
        else:
            text = self.completion_client.complete(model_name, messages)
        self.last_model = model_name
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as error:
            raise ModuleExecutionError(
                f"LLM 출력을 JSON으로 파싱할 수 없습니다: {text}"
            ) from error
        if not isinstance(parsed, list):
            raise ModuleExecutionError("LLM 출력은 JSON 배열이어야 합니다")
        try:
            normalized = normalize_subqueries(parsed)
        except ValueError as error:
            raise ModuleExecutionError(str(error)) from error
        return {
            "query_context": input_data.query_context.model_dump(mode="json"),
            "subqueries": augment_subqueries(normalized),
        }


# ==============================================================================
# 2. Adaptive Query Decomposer Module
# ==============================================================================

class AdaptiveQueryDecomposerInput(ModuleInputDTO):
    query_context: QueryContextDTO
    semantic_match: SemanticQueryMatchOutput = Field(
        description="Semantic Query Matcher의 라우팅 결과"
    )


from modules.common.config import DEFAULT_PLAN_REUSE_THRESHOLD


class AdaptiveQueryDecomposerConfig(DecomposerConfigDTO):
    plan_reuse_threshold: float = Field(
        default=DEFAULT_PLAN_REUSE_THRESHOLD,
        ge=0,
        le=1,
        description="카탈로그 분해 계획을 재사용할 최소 시맨틱 신뢰도",
    )


class AdaptiveQueryDecomposerExecutionDTO(AdaptiveQueryDecomposerInput, AdaptiveQueryDecomposerConfig):
    """Runtime input combining graph values with the decomposer settings."""


class AdaptiveQueryDecomposerModule(BaseModule):
    """Avoid the decomposition call when the example-query route is confident."""

    definition = ModuleDefinition(
        type="adaptive_query_decomposer",
        label="Adaptive Query Decomposer",
        category="Logic",
        description="시맨틱 계획의 신뢰도와 질문 제약을 검증해 안전할 때만 재사용하고, 그 외에는 LLM으로 서브쿼리를 분해합니다.",
        inputs=["query_context", "semantic_match"],
        outputs=["output"],
        config_fields=[
            "model", "preset", "system_prompt", "user_prompt_template",
            "plan_reuse_threshold",
        ],
        raw_output=True,
        version="2",
    )
    input_model = AdaptiveQueryDecomposerInput
    config_model = AdaptiveQueryDecomposerConfig
    execution_model = AdaptiveQueryDecomposerExecutionDTO
    output_model = SubqueriesDTO

    def __init__(self, completion_client: Optional[ChatCompletionClient] = None) -> None:
        self.decomposer = DecomposerModule(completion_client=completion_client)

    def execute(
        self,
        input_data: AdaptiveQueryDecomposerInput,
        config: Optional[AdaptiveQueryDecomposerConfig] = None,
    ) -> Dict[str, Any]:
        if config is None and isinstance(input_data, AdaptiveQueryDecomposerExecutionDTO):
            cfg = input_data
        else:
            cfg = config or AdaptiveQueryDecomposerConfig()
        # Module instances may be reused by the in-process executor. Clear
        # previous telemetry so a safe reuse is never reported as an LLM call.
        self.last_usage = None
        self.last_model = cfg.model
        match = input_data.semantic_match
        validation = validate_plan_reuse(
            input_data.query_context.question_text,
            match.target,
            match.subqueries,
        )
        if (
            match.matched
            and match.confidence >= cfg.plan_reuse_threshold
            and validation.reusable
        ):
            subqueries = augment_subqueries(match.subqueries)
            return {
                "query_context": QueryContextDTO(
                    question_id=input_data.query_context.question_id,
                    question_text=input_data.query_context.question_text,
                ).model_dump(mode="json"),
                "subqueries": subqueries,
            }
        # Low-confidence, missing, or constraint-mismatched plans must be
        # regenerated rather than silently reusing a nearby example's plan.
        result = self.decomposer.execute(
            DecomposerInputDTO(
                query_context=input_data.query_context,
            ),
            config=DecomposerConfigDTO(
                model=cfg.model,
                preset=cfg.preset,
                system_prompt=cfg.system_prompt,
                user_prompt_template=cfg.user_prompt_template,
            ),
        )
        self.last_usage = getattr(self.decomposer, "last_usage", None)
        self.last_model = getattr(self.decomposer, "last_model", cfg.model)
        return result

# ==============================================================================
# 3. Template Query Decomposer Module
# ==============================================================================

@dataclass(frozen=True)
class MetricTemplate:
    row_header: str
    sheet: str
    aliases: tuple[str, ...]


# These are sheet/row values present in the indexed financial workbooks.  The
# list is deliberately closed: unknown metrics go to the LLM rather than being
# guessed from a nearby phrase.
METRIC_TEMPLATES: tuple[MetricTemplate, ...] = (
    MetricTemplate("Cash and Short-Term Investments", "Balance_Sheet", ("현금과 단기투자", "현금 및 단기투자", "단기투자자산", "cash and short-term investments", "cash & st investments")),
    MetricTemplate("Capital Expenditure", "Cash_Flow", ("capital expenditure", "자본지출", "투자지출", "capex")),
    MetricTemplate("Cash from Ops.", "Cash_Flow", ("영업활동 현금흐름", "영업현금흐름", "operating cash flow", "cash from ops")),
    MetricTemplate("Total Enterprise Value", "Key_Stats", ("total enterprise value", "enterprise value", "시가총액과 tev", "tev")),
    MetricTemplate("Market Capitalization", "Key_Stats", ("market capitalization", "market cap", "시가총액")),
    MetricTemplate("Long-Term Debt", "Balance_Sheet", ("long-term debt", "long term debt", "장기부채")),
    MetricTemplate("Total Liabilities", "Balance_Sheet", ("total liabilities", "총부채")),
    MetricTemplate("Total Assets", "Balance_Sheet", ("total assets", "총자산")),
    MetricTemplate("Current Ratio", "Key_Stats", ("current ratio", "유동비율")),
    MetricTemplate("Return on Equity", "Key_Stats", ("return on equity", "roe")),
    MetricTemplate("Return on Assets", "Key_Stats", ("return on assets", "roa")),
    MetricTemplate("Diluted EPS", "Income_Statement", ("diluted eps", "희석 eps", "주당순이익")),
    MetricTemplate("Dividends per Share", "Income_Statement", ("dividends per share", "주당배당", "dps")),
    MetricTemplate("Operating Income", "Income_Statement", ("operating income", "operating profit", "영업이익", "ebit")),
    MetricTemplate("Gross Profit", "Income_Statement", ("gross profit", "매출총이익")),
    MetricTemplate("Total Revenue", "Income_Statement", ("total revenue", "net sales", "revenue", "총매출", "매출")),
    MetricTemplate("Net Income", "Income_Statement", ("net income", "순이익")),
    MetricTemplate("EBITDA", "Income_Statement", ("ebitda",)),
    MetricTemplate("Shares Outstanding", "Key_Stats", ("shares outstanding", "발행주식")),
)

_YEAR = re.compile(r"(?<!\d)(20(?:2[0-9]))(?!\d)")
_LTM = re.compile(r"최근\s*12\s*개월|last\s+twelve\s+months|(?<![a-z0-9])(?:ltm|ttm)(?![a-z0-9])", re.I)
_UNSAFE_INTENT = re.compile(r"\b(?:ceo|cfo|chairman)\b|최고경영자|대표이사|주요\s*주주|대주주|지분", re.I)


def _contains(text: str, alias: str) -> bool:
    if re.fullmatch(r"[a-z0-9 .&-]+", alias, flags=re.I):
        return re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", text, flags=re.I) is not None
    return alias.casefold() in text.casefold()


def _periods(question: str) -> tuple[str, ...]:
    if _LTM.search(question):
        return ("LTM",)
    years = sorted({int(value) for value in _YEAR.findall(question)})
    return tuple(f"FY{year}" for year in years)


def _metrics(question: str) -> tuple[MetricTemplate, ...]:
    lowered = question.casefold()
    # Calculation concepts are expanded to their required source cells.
    if any(term in lowered for term in ("free cash flow", "잉여현금흐름", "fcf")):
        wanted = {"Cash from Ops.", "Capital Expenditure"}
        return tuple(item for item in METRIC_TEMPLATES if item.row_header in wanted)
    if any(term in lowered for term in ("gross margin", "매출총이익률")):
        wanted = {"Gross Profit", "Total Revenue"}
        return tuple(item for item in METRIC_TEMPLATES if item.row_header in wanted)
    matches = [
        (len(alias), template)
        for template in METRIC_TEMPLATES
        for alias in template.aliases
        if _contains(question, alias)
    ]
    # Prefer the longest expression and retain non-overlapping canonical rows.
    selected: list[MetricTemplate] = []
    for _, template in sorted(matches, key=lambda item: (-item[0], item[1].row_header)):
        if template.row_header not in {item.row_header for item in selected}:
            selected.append(template)
    return tuple(selected)


def build_template_subqueries(question: str) -> tuple[list[str] | None, str]:
    """Create only a fully explicit, workbook-supported retrieval plan."""

    if _UNSAFE_INTENT.search(question):
        return None, "company-profile or ownership intent is not a financial-cell template"
    periods = _periods(question)
    if not periods:
        return None, "no explicit fiscal period or LTM slot"
    metrics = _metrics(question)
    if not metrics:
        return None, "no verified financial metric slot"
    subqueries = [
        serialize_structured_query(sheet=item.sheet, row_header=item.row_header, column_header=period)
        for item in metrics
        for period in periods
    ]
    return augment_subqueries(subqueries), "filled verified metric/period templates"


class TemplateQueryDecomposerExecutionDTO(AdaptiveQueryDecomposerInput, AdaptiveQueryDecomposerConfig):
    """Runtime input for deterministic templates followed by adaptive fallback."""


class TemplateQueryDecomposerModule(BaseModule):
    definition = ModuleDefinition(
        type="template_query_decomposer",
        label="Template Query Decomposer",
        category="Logic",
        description="질문의 재무 지표·기간 슬롯으로 검증된 검색 템플릿을 채우고, 불완전한 경우에만 LLM 분해로 폴백합니다.",
        inputs=["query_context", "semantic_match"],
        outputs=["output"],
        config_fields=["model", "preset", "system_prompt", "user_prompt_template", "plan_reuse_threshold"],
        raw_output=True,
        version="1",
    )
    input_model = AdaptiveQueryDecomposerInput
    config_model = AdaptiveQueryDecomposerConfig
    execution_model = TemplateQueryDecomposerExecutionDTO
    output_model = SubqueriesDTO

    def __init__(self, completion_client: Optional[ChatCompletionClient] = None) -> None:
        self.fallback = AdaptiveQueryDecomposerModule(completion_client=completion_client)
        self.last_decision = "not executed"

    def execute(
        self,
        input_data: AdaptiveQueryDecomposerInput,
        config: Optional[AdaptiveQueryDecomposerConfig] = None,
    ) -> Dict[str, Any]:
        if config is None and isinstance(input_data, TemplateQueryDecomposerExecutionDTO):
            cfg = input_data
        else:
            cfg = config or AdaptiveQueryDecomposerConfig()
        self.last_usage = None
        self.last_model = cfg.model
        question = input_data.query_context.question_text
        subqueries, reason = build_template_subqueries(question)
        if subqueries:
            self.last_decision = f"template_reuse: {reason}"
            return {
                "query_context": input_data.query_context.model_dump(mode="json"),
                "subqueries": subqueries,
            }

        self.last_decision = f"llm_fallback: {reason}"
        result = self.fallback.execute(input_data, config=cfg)
        self.last_usage = getattr(self.fallback, "last_usage", None)
        self.last_model = getattr(self.fallback, "last_model", cfg.model)
        return result

# ==============================================================================
# 4. Thesaurus Decomposer Module
# ==============================================================================

class ThesaurusDecomposerInputDTO(ModuleInputDTO):
    query_context: QueryContextDTO = Field(
        description="질문 메타데이터 및 질문 본문을 포함하는 계보 DTO"
    )


from modules.common.config import DEFAULT_LLM_MODEL


class ThesaurusDecomposerConfigDTO(ModuleConfigDTO):
    model: str = Field(
        default=DEFAULT_LLM_MODEL,
        description="서브쿼리 분해에 사용할 LLM 모델 ID",
    )
    preset: str = Field(
        default="luna_thesaurus_decomposer",
        description="Decomposer 프롬프트 프리셋 ID",
    )
    system_prompt: str = Field(
        default=LUNA_SYSTEM_PROMPT,
        description="표준 시소러스 가이드가 포함된 시스템 프롬프트",
    )
    user_prompt_template: str = Field(
        default=LUNA_USER_TEMPLATE,
        description="{question} 템플릿 변수를 포함하는 사용자 프롬프트",
    )


class ThesaurusDecomposerExecutionDTO(
    ThesaurusDecomposerInputDTO, ThesaurusDecomposerConfigDTO
):
    """Execution DTO for Thesaurus-augmented Decomposer."""


class ThesaurusDecomposerModule(BaseModule):
    definition = ModuleDefinition(
        type="thesaurus_decomposer",
        label="Thesaurus Financial Decomposer",
        category="Logic",
        description="재무 지표 사전(Thesaurus)을 참조하여 질문을 정밀한 표준 서브쿼리로 분해합니다.",
        inputs=["query_context"],
        outputs=["subqueries"],
        config_fields=[
            "model",
            "preset",
            "system_prompt",
            "user_prompt_template",
        ],
        raw_output=True,
        version="1",
    )
    input_model = ThesaurusDecomposerInputDTO
    config_model = ThesaurusDecomposerConfigDTO
    execution_model = ThesaurusDecomposerExecutionDTO
    output_model = SubqueriesDTO

    def __init__(
        self,
        completion_client: Optional[ChatCompletionClient] = None,
    ) -> None:
        self.completion_client = completion_client

    def execute(
        self,
        input_data: ThesaurusDecomposerInputDTO,
        config: Optional[ThesaurusDecomposerConfigDTO] = None,
    ) -> Dict[str, Any]:
        if config is None and isinstance(input_data, ThesaurusDecomposerExecutionDTO):
            cfg = input_data
        else:
            cfg = config or ThesaurusDecomposerConfigDTO()
        question_text = input_data.query_context.question_text
        query_context_dict = input_data.query_context.model_dump(mode="json")

        if not question_text:
            return {
                "query_context": query_context_dict,
                "subqueries": [],
            }

        client = self.completion_client or ChatCompletionClient()

        preset_data = DECOMPOSER_PRESETS.get(cfg.preset, {})
        system_prompt = cfg.system_prompt or preset_data.get(
            "system_prompt", LUNA_SYSTEM_PROMPT
        )
        user_template = cfg.user_prompt_template or preset_data.get(
            "user_prompt_template", LUNA_USER_TEMPLATE
        )

        # Inject financial thesaurus guidance dynamically
        thesaurus_guide = format_thesaurus_prompt_guide(question_text)
        if thesaurus_guide:
            system_prompt = system_prompt + "\n" + thesaurus_guide

        user_content = user_template.format(question=question_text)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            result: ChatCompletionResult = client.complete_with_metadata(
                model=cfg.model,
                messages=messages,
            )
        except ChatCompletionError as e:
            raise ModuleExecutionError(f"LLM API 호출 실패: {e}") from e

        try:
            parsed = json.loads(result.content)
            if isinstance(parsed, list):
                subqueries_raw = parsed
            elif isinstance(parsed, dict):
                raw_val = parsed.get("subqueries", [])
                if isinstance(raw_val, str):
                    subqueries_raw = [raw_val]
                elif isinstance(raw_val, list):
                    subqueries_raw = raw_val
                else:
                    subqueries_raw = [str(raw_val)] if raw_val is not None else []
            elif isinstance(parsed, str):
                subqueries_raw = [parsed]
            else:
                subqueries_raw = [str(parsed)]
            subqueries = list(
                dict.fromkeys([str(q).strip() for q in subqueries_raw if str(q).strip()])
            )
        except json.JSONDecodeError:
            # Fallback: extract list using regex
            import re
            matches = re.findall(r'"([^"]+)"', result.content)
            subqueries = list(dict.fromkeys([m.strip() for m in matches if m.strip()]))

        self.last_usage = getattr(result, "usage", {}) or {}
        self.last_model = cfg.model
        self.last_latency = getattr(result, "latency_seconds", 0.0)

        return {
            "query_context": query_context_dict,
            "subqueries": subqueries,
        }

# ==============================================================================
# 5. Direct Query Decomposer Module
# ==============================================================================

class DirectQueryDecomposerInput(ModuleInputDTO):
    query_context: QueryContextDTO


class DirectQueryDecomposerModule(BaseModule):
    definition = ModuleDefinition(
        type="direct_query_decomposer",
        label="Direct Query Baseline",
        category="Logic",
        description="LLM 분해 없이 원본 질문 하나를 그대로 검색 쿼리로 전달합니다.",
        inputs=["query_context"],
        outputs=["output"],
        raw_output=True,
        version="1",
    )
    input_model = DirectQueryDecomposerInput
    config_model = EmptyModuleConfigDTO
    output_model = SubqueriesDTO

    def execute(
        self,
        input_data: DirectQueryDecomposerInput,
        config: Optional[EmptyModuleConfigDTO] = None,
    ) -> Dict[str, Any]:
        return {
            "query_context": QueryContextDTO(
                question_id=input_data.query_context.question_id,
                question_text=input_data.query_context.question_text,
            ).model_dump(mode="json"),
            "subqueries": [input_data.query_context.question_text],
        }


__all__ = [
    "AdaptiveQueryDecomposerConfig",
    "AdaptiveQueryDecomposerExecutionDTO",
    "AdaptiveQueryDecomposerInput",
    "AdaptiveQueryDecomposerModule",
    "DECOMPOSER_PRESETS",
    "DECOMPOSER_SYSTEM_PROMPT",
    "DECOMPOSER_USER_TEMPLATE",
    "DecomposerConfigDTO",
    "DecomposerExecutionDTO",
    "DecomposerInputDTO",
    "DecomposerModule",
    "DirectQueryDecomposerInput",
    "DirectQueryDecomposerModule",
    "LUNA_SYSTEM_PROMPT",
    "LUNA_USER_TEMPLATE",
    "METRIC_EQUIVALENT_GROUPS",
    "MetricTemplate",
    "PERIOD_EQUIVALENT_GROUPS",
    "RDB_FINANCIAL_SYSTEM_PROMPT",
    "SIMPLE_SYSTEM_PROMPT",
    "SubqueriesDTO",
    "TemplateQueryDecomposerConfig",
    "TemplateQueryDecomposerExecutionDTO",
    "TemplateQueryDecomposerInput",
    "TemplateQueryDecomposerModule",
    "ThesaurusDecomposerConfigDTO",
    "ThesaurusDecomposerExecutionDTO",
    "ThesaurusDecomposerInputDTO",
    "ThesaurusDecomposerModule",
    "UNKNOWN_FIELD",
    "augment_subqueries",
    "decomposer_config_presets",
    "normalize_structured_query",
    "normalize_subqueries",
    "serialize_structured_query",
]

