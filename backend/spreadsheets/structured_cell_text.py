import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from .cell_visibility import WorksheetVisibility


UNKNOWN_FIELD = "?"
SERIALIZATION_VERSION = "structured-cell-v5-visible-only"
SHEET_NAME_ALIASES = {
    "balance sheet": "Balance_Sheet",
    "balance_sheet": "Balance_Sheet",
    "income statement": "Income_Statement",
    "income_statement": "Income_Statement",
    "cash flow": "Cash_Flow",
    "cash flow statement": "Cash_Flow",
    "cash_flow": "Cash_Flow",
    "key stats": "Key_Stats",
    "key statistics": "Key_Stats",
    "key_stats": "Key_Stats",
}
SHEET_CODE_MAP = {
    "Balance_Sheet": "BS",
    "Income_Statement": "IS",
    "Cash_Flow": "CF",
    "Key_Stats": "KS",
}
PERIOD_PATTERN = re.compile(
    r"\b(?:19|20)\d{2}(?:-\d{2}-\d{2})?\b|\bFY(?:-?\d+|\d{4})\b|\bLTM\b",
    re.IGNORECASE,
)


def canonical_sheet_name(sheet_name: str) -> str:
    normalized = sheet_name.strip()
    return SHEET_NAME_ALIASES.get(normalized.lower(), normalized)


def sheet_code(sheet_name: str) -> str:
    canonical = canonical_sheet_name(sheet_name)
    return SHEET_CODE_MAP.get(canonical, canonical)


def format_cell_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    formatted = str(value).strip()
    return formatted or None


def serialize_structured_cell(
    sheet_name: str,
    row_headers: List[str],
    column_headers: List[str],
    cell_value: str = UNKNOWN_FIELD,
) -> str:
    row_text = " > ".join(row_headers) if row_headers else UNKNOWN_FIELD
    column_text = " > ".join(column_headers) if column_headers else UNKNOWN_FIELD
    value_text = cell_value if cell_value else UNKNOWN_FIELD
    return (
        f"Sheet: {canonical_sheet_name(sheet_name) or UNKNOWN_FIELD} | "
        f"Row Header: {row_text} | "
        f"Column Header: {column_text} | "
        f"Cell Value: {value_text}"
    )


def generate_header_combinations(
    row_headers: List[str],
    column_headers: List[str],
) -> List[Tuple[List[str], List[str]]]:
    """Generate the comprehensive full header path plus granular single/sub-level header combinations."""
    if not row_headers and not column_headers:
        return [([], [])]

    def _sub_variants(headers: List[str]) -> List[List[str]]:
        if not headers:
            return [[]]
        variants: List[List[str]] = []
        seen: set[Tuple[str, ...]] = set()

        def _add(variant: List[str]):
            key = tuple(variant)
            if key and key not in seen:
                seen.add(key)
                variants.append(variant)

        # 1. Full chain (Comprehensive)
        _add(headers)

        # 2. Individual single items (e.g. leaf metric, individual categories)
        for h in headers:
            _add([h])

        # 3. Cumulative prefix sub-paths (e.g., A, A > B, A > B > C)
        for i in range(1, len(headers)):
            _add(headers[:i])

        # 4. Suffix sub-paths (e.g., B > C)
        for i in range(1, len(headers)):
            _add(headers[i:])

        return variants or [headers]

    row_variants = _sub_variants(row_headers)
    col_variants = _sub_variants(column_headers)

    combinations: List[Tuple[List[str], List[str]]] = []
    seen_combos: set[Tuple[Tuple[str, ...], Tuple[str, ...]]] = set()

    # Always put full comprehensive format first
    primary = (row_headers, column_headers)
    key_primary = (tuple(row_headers), tuple(column_headers))
    seen_combos.add(key_primary)
    combinations.append(primary)

    for r_var in row_variants:
        for c_var in col_variants:
            key = (tuple(r_var), tuple(c_var))
            if key not in seen_combos:
                seen_combos.add(key)
                combinations.append((r_var, c_var))

    return combinations


class WorksheetValueReader:
    """Read visible worksheet values while resolving merged-cell anchors."""

    def __init__(self, worksheet) -> None:
        self.worksheet = worksheet
        self.visibility = WorksheetVisibility.from_worksheet(worksheet)
        self._merged_anchors: Dict[Tuple[int, int], Tuple[int, int]] = {}
        for merged_range in worksheet.merged_cells.ranges:
            anchor = (merged_range.min_row, merged_range.min_col)
            for row in range(merged_range.min_row, merged_range.max_row + 1):
                for column in range(merged_range.min_col, merged_range.max_col + 1):
                    self._merged_anchors[(row, column)] = anchor

    def value(self, row: int, column: int) -> Optional[str]:
        if not self.visibility.cell_visible(row, column):
            return None
        source_row, source_column = self._merged_anchors.get(
            (row, column),
            (row, column),
        )
        if not self.visibility.cell_visible(source_row, source_column):
            return None
        return format_cell_value(
            self.worksheet.cell(row=source_row, column=source_column).value
        )

    def row_hidden(self, row: int) -> bool:
        return self.visibility.row_hidden(row)

    def column_hidden(self, column: int) -> bool:
        return self.visibility.column_hidden(column)


def ensure_period_header(headers: List[str]) -> List[str]:
    if any(PERIOD_PATTERN.search(header) for header in headers):
        return headers
    return [*headers, "LTM"]
