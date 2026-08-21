"""Slot-based financial query decomposition with a safe LLM fallback.

This module intentionally does not copy a historical question's plan.  It
extracts explicit period and financial-metric slots from the new question and
fills a small set of verified retrieval templates instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, cast

from pydantic import BaseModel

from backend.providers.llm.chat_completion import ChatCompletionClient
from modules.query.adaptive_query_decomposer import (
    AdaptiveQueryDecomposerConfig,
    AdaptiveQueryDecomposerInput,
    AdaptiveQueryDecomposerModule,
)
from modules.common.base_module import BaseModule, ModuleDefinition, QueryContextDTO
from modules.query.decomposer import SubqueriesDTO
from modules.query.subquery_format import augment_subqueries, serialize_structured_query


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

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        input_data = cast(TemplateQueryDecomposerExecutionDTO, payload)
        self.last_usage = None
        self.last_model = input_data.model
        question = input_data.query_context.question_text
        subqueries, reason = build_template_subqueries(question)
        if subqueries:
            self.last_decision = f"template_reuse: {reason}"
            return {
                "query_context": input_data.query_context.model_dump(mode="json"),
                "subqueries": subqueries,
            }

        self.last_decision = f"llm_fallback: {reason}"
        result = self.fallback.execute(input_data)
        self.last_usage = getattr(self.fallback, "last_usage", None)
        self.last_model = getattr(self.fallback, "last_model", input_data.model)
        return result
