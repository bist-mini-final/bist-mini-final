import re
from typing import Iterable, List, Sequence


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
    sheet = sheet_aliases.get(sheet.lower(), sheet)
    return serialize_structured_query(
        sheet=sheet,
        row_header=fields.get("row header", UNKNOWN_FIELD),
        column_header=fields.get("column header", UNKNOWN_FIELD),
        cell_value=fields.get("cell value", UNKNOWN_FIELD),
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
