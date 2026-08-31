"""Provider-neutral structured-cell value parsing rules."""

import re
from datetime import date, datetime
from typing import Any, Final

UNRESOLVED_CELL_VALUES: Final = frozenset(
    {"", "?", "-", "na", "n/a", "nm", "#pend", "none", "null"}
)
CELL_VALUE_PATTERN = re.compile(
    r"(?:^|\|)\s*Cell Value:\s*([^|]*)",
    re.IGNORECASE,
)


def format_cell_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    formatted = str(value).strip()
    return formatted or None


def resolved_cell_value(value: Any) -> str | None:
    """Return a concrete cell value, excluding search placeholders."""

    formatted = format_cell_value(value)
    if formatted is None or formatted.casefold() in UNRESOLVED_CELL_VALUES:
        return None
    return formatted


def extract_resolved_cell_value(source_text: Any) -> str | None:
    """Extract a concrete value from the canonical structured-cell text."""

    matched = CELL_VALUE_PATTERN.search(str(source_text or ""))
    if matched is None:
        return None
    return resolved_cell_value(matched.group(1))


__all__ = [
    "UNRESOLVED_CELL_VALUES",
    "extract_resolved_cell_value",
    "format_cell_value",
    "resolved_cell_value",
]
