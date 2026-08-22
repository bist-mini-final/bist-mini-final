"""Shared parsing of structured subquery company and sheet scope fields."""

from __future__ import annotations

from typing import List, Optional, Tuple


def extract_query_scope(
    query_text: str,
    fallback_company: Optional[str] = None,
    fallback_sheets: Optional[List[str]] = None,
) -> Tuple[Optional[str], Optional[List[str]]]:
    """Parse canonical Company and Sheet fields with optional routed fallbacks."""
    company = fallback_company
    sheets = fallback_sheets
    if not isinstance(query_text, str):
        return company, sheets

    for part in (value.strip() for value in query_text.split("|")):
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        normalized_key = key.strip().lower()
        normalized_value = value.strip()
        if normalized_key == "company" and normalized_value not in ("", "?"):
            company = normalized_value
        elif normalized_key == "sheet" and normalized_value not in ("", "?"):
            sheets = [normalized_value]
    return company, sheets


__all__ = ["extract_query_scope"]
