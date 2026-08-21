from __future__ import annotations

"""Forwarding helpers from modules/query/decomposer.py for backwards compatibility."""

from modules.query.decomposer import (
    METRIC_EQUIVALENT_GROUPS,
    PERIOD_EQUIVALENT_GROUPS,
    UNKNOWN_FIELD,
    augment_subqueries,
    normalize_structured_query,
    normalize_subqueries,
    serialize_structured_query,
)

__all__ = [
    "METRIC_EQUIVALENT_GROUPS",
    "PERIOD_EQUIVALENT_GROUPS",
    "UNKNOWN_FIELD",
    "augment_subqueries",
    "normalize_structured_query",
    "normalize_subqueries",
    "serialize_structured_query",
]
