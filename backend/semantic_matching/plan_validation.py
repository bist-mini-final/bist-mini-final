"""Deterministic safety checks for reusing a catalog decomposition plan."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

_YEAR_PATTERN = re.compile(r"(?<!\d)(20(?:2[0-9]))(?!\d)")
_SHORT_KOREAN_YEAR_PATTERN = re.compile(r"(?<!\d)(\d{2})\s*년")
_RECENT_PERIOD_PATTERN = re.compile(r"최근\s*(\d+)\s*(?:개년|년)")
_LTM_PATTERN = re.compile(
    r"최근\s*12\s*개월|last\s+twelve\s+months|(?<![a-z0-9])ltm(?![a-z0-9])",
    re.IGNORECASE,
)
_TREND_PATTERN = re.compile(r"추이|흐름|연도별|trend|cagr|yoy", re.IGNORECASE)
_CALCULATION_PATTERN = re.compile(
    r"계산|비교|차이|각각|증감|성장률|마진|비율|배수|cagr|yoy|versus|\bvs\b",
    re.IGNORECASE,
)


_ENTITY_ALIASES = {
    "ibm": ("ibm",),
    "bac": ("bac", "bank of america", "뱅크 오브 아메리카"),
    "virtual_company": ("virtual company", "가상기업", "가상 기업"),
}


_METRIC_ALIASES = {
    "revenue": ("매출", "revenue", "net sales"),
    "gross_profit": ("매출총이익", "gross profit"),
    "ebitda": ("ebitda",),
    "operating_income": ("영업이익", "operating income", "operating profit", "ebit"),
    "net_income": ("순이익", "net income"),
    "eps": ("희석 eps", "주당순이익", "diluted eps", "earnings per share"),
    "dps": ("dps", "주당배당", "dividends per share"),
    "cash": ("현금", "단기투자", "cash and short-term", "cash & st investments"),
    "assets": ("총자산", "total assets"),
    "liabilities": ("총부채", "total liabilities"),
    "long_term_debt": ("장기부채", "long-term debt", "long term debt"),
    "operating_cash_flow": ("영업현금흐름", "cash from ops", "operating cash flow"),
    "capex": ("capex", "자본지출", "투자지출", "capital expenditure"),
    "market_cap": ("시가총액", "market capitalization", "market cap"),
    "tev": ("tev", "total enterprise value", "enterprise value"),
    "shares": ("발행주식", "shares outstanding"),
    "current_ratio": ("유동비율", "current ratio"),
    "roe": ("roe", "return on equity"),
    "roa": ("roa", "return on assets"),
}


@dataclass(frozen=True)
class PlanValidation:
    reusable: bool
    reason: str


@dataclass(frozen=True)
class PlanSignature:
    metrics: tuple[str, ...]
    periods: tuple[int, ...]
    sheets: tuple[str, ...] = ()


def _contains_alias(text: str, alias: str) -> bool:
    if re.fullmatch(r"[a-z0-9 /&.-]+", alias, flags=re.IGNORECASE):
        return re.search(
            rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])",
            text,
            flags=re.IGNORECASE,
        ) is not None
    return alias.casefold() in text.casefold()


def _question_entities(question: str) -> set[str]:
    return {
        entity
        for entity, aliases in _ENTITY_ALIASES.items()
        if any(_contains_alias(question, alias) for alias in aliases)
    }


def _target_entity(target: str | None) -> str | None:
    lowered = (target or "").casefold()
    if "ibm" in lowered:
        return "ibm"
    if "bac" in lowered:
        return "bac"
    if "virtual_company" in lowered:
        return "virtual_company"
    return None


def _question_years(question: str) -> set[int]:
    years = {int(value) for value in _YEAR_PATTERN.findall(question)}
    years.update(
        2000 + int(value)
        for value in _SHORT_KOREAN_YEAR_PATTERN.findall(question)
        if 20 <= int(value) <= 29
    )
    range_match = re.search(
        r"(20(?:2[0-9]))\s*년?\s*(?:부터|~|～|-)\s*(20(?:2[0-9]))",  # noqa: RUF001
        question,
    )
    if range_match:
        start, end = (int(value) for value in range_match.groups())
        if start <= end and end - start <= 10:
            years.update(range(start, end + 1))
    if _LTM_PATTERN.search(question):
        # The indexed financial data aliases LTM to the current FY0/FY2025
        # reporting period, so it must participate in the same safety check.
        years.add(2025)
    return years


def _is_trend_question(question: str) -> bool:
    # "영업현금흐름" and "현금흐름" are metric names, not requests for a
    # time-series trend. Remove them before looking for the standalone concept.
    without_cash_flow_metric = re.sub(
        r"영업\s*현금\s*흐름|현금\s*흐름",
        "",
        question,
        flags=re.IGNORECASE,
    )
    return _TREND_PATTERN.search(without_cash_flow_metric) is not None


def _plan_fields(subqueries: Iterable[str]) -> list[dict[str, str]] | None:
    fields: list[dict[str, str]] = []
    try:
        for subquery in subqueries:
            parsed: dict[str, str] = {}
            for part in subquery.split("|"):
                key, separator, value = part.partition(":")
                if separator:
                    parsed[key.strip().casefold()] = value.strip()
            if parsed:
                fields.append(parsed)
    except (TypeError, ValueError):
        return None
    return fields or None


def _plan_years(fields: Iterable[dict[str, str]]) -> set[int]:
    field_list = list(fields)
    years = {
        int(value)
        for field in field_list
        for value in _YEAR_PATTERN.findall(field.get("column header", ""))
    }
    if any(
        re.search(r"(?<![a-z0-9])ltm(?![a-z0-9])", field.get("column header", ""), re.IGNORECASE)
        for field in field_list
    ):
        # The project's period expansion treats LTM, FY0, and FY2025 as
        # equivalent representations of the current reporting period.
        years.add(2025)
    return years


def _extract_metrics(text: str) -> set[str]:
    """Prefer longer aliases so embedded terms do not create false metrics."""

    candidates: list[tuple[int, int, str]] = []
    for metric, aliases in _METRIC_ALIASES.items():
        for alias in aliases:
            if re.fullmatch(r"[a-z0-9 /&.-]+", alias, flags=re.IGNORECASE):
                pattern = rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"
            else:
                pattern = re.escape(alias)
            candidates.extend(
                (match.start(), match.end(), metric)
                for match in re.finditer(pattern, text, flags=re.IGNORECASE)
            )

    selected: list[tuple[int, int]] = []
    metrics: set[str] = set()
    for start, end, metric in sorted(
        candidates,
        key=lambda item: (-(item[1] - item[0]), item[0], item[2]),
    ):
        if any(start < used_end and end > used_start for used_start, used_end in selected):
            continue
        selected.append((start, end))
        metrics.add(metric)
    return metrics


def _question_metrics(question: str) -> set[str]:
    return _extract_metrics(question)


def _plan_metrics(fields: Iterable[dict[str, str]]) -> set[str]:
    row_headers = "\n".join(field.get("row header", "") for field in fields)
    return _extract_metrics(row_headers)


def validate_plan_reuse(
    question: str,
    target: str | None,
    subqueries: Iterable[str],
) -> PlanValidation:
    """Reject a catalog plan when explicit query constraints are not preserved."""

    fields = _plan_fields(subqueries)
    if fields is None:
        return PlanValidation(False, "catalog plan is empty or not a structured query")

    entities = _question_entities(question)
    target_entity = _target_entity(target)
    if entities and (target_entity is None or target_entity not in entities):
        return PlanValidation(False, "question entity does not match the routed target")

    expected_years = _question_years(question)
    actual_years = _plan_years(fields)
    if expected_years and actual_years != expected_years:
        return PlanValidation(
            False,
            f"question periods {sorted(expected_years)} do not match plan periods {sorted(actual_years)}",
        )

    recent_match = _RECENT_PERIOD_PATTERN.search(question)
    if recent_match and len(actual_years) < int(recent_match.group(1)):
        return PlanValidation(False, "plan does not cover the requested recent-year count")
    if _is_trend_question(question) and len(actual_years) < 2:
        return PlanValidation(False, "trend question requires at least two plan periods")

    expected_metrics = _question_metrics(question)
    actual_metrics = _plan_metrics(fields)
    if expected_metrics and not expected_metrics.issubset(actual_metrics):
        missing = sorted(expected_metrics - actual_metrics)
        return PlanValidation(False, f"plan is missing requested metrics: {missing}")

    if _CALCULATION_PATTERN.search(question):
        distinct_rows = {
            field.get("row header", "").casefold()
            for field in fields
            if field.get("row header", "") not in {"", "?"}
        }
        if len(distinct_rows) * max(1, len(actual_years)) < 2:
            return PlanValidation(False, "calculation/comparison question needs multiple retrieval inputs")

    return PlanValidation(True, "question constraints match the catalog plan")


def plan_signature(subqueries: Iterable[str]) -> PlanSignature | None:
    """Return canonical metrics and periods for benchmark scoring."""

    fields = _plan_fields(subqueries)
    if fields is None:
        return None
    return PlanSignature(
        metrics=tuple(sorted(_plan_metrics(fields))),
        periods=tuple(sorted(_plan_years(fields))),
        sheets=tuple(sorted({
            value
            for field in fields
            if (value := field.get("sheet", "").strip()) not in {"", "?"}
        }, key=str.casefold)),
    )
