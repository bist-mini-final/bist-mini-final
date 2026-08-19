"""Loader for the shared semantic-query example catalog."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ..core.settings import PROJECT_DIR


DEFAULT_CATALOG_PATH = PROJECT_DIR / "data" / "semantic_query_plans.json"


@dataclass(frozen=True)
class QueryExample:
    example_id: str
    question: str
    target: str
    sheets: tuple[str, ...]
    query_type: int | None = None
    subqueries: tuple[str, ...] = ()


@lru_cache(maxsize=4)
def load_examples(path: str = str(DEFAULT_CATALOG_PATH)) -> tuple[QueryExample, ...]:
    """Load valid catalog entries once per file path.

    The catalog remains outside the app package so it can keep being shared with
    the original semantic-query-matching experiment.
    """

    catalog_path = Path(path)
    try:
        raw_items = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read semantic query catalog: {catalog_path}") from error

    examples = []
    for raw in raw_items:
        question = str(raw.get("question") or "").strip()
        target = str(raw.get("target") or "").strip()
        if not question or not target:
            continue
        metadata = raw.get("metadata") or {}
        raw_sheets = metadata.get("sheets") or ([metadata.get("sheet")] if metadata.get("sheet") else [])
        sheets = tuple(str(sheet).strip() for sheet in raw_sheets if str(sheet).strip())
        raw_plan = raw.get("decomposition") or {}
        examples.append(
            QueryExample(
                example_id=str(raw.get("id") or ""),
                question=question,
                target=target,
                sheets=sheets,
                query_type=int(metadata["query_type"]) if metadata.get("query_type") else None,
                subqueries=tuple(str(item) for item in raw_plan.get("subqueries", []) if str(item).strip()),
            )
        )
    if not examples:
        raise ValueError(f"Semantic query catalog is empty: {catalog_path}")
    return tuple(examples)
