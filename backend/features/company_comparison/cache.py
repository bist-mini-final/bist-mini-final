from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import unicodedata
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from backend.features.bi.models import BiDashboardSnapshot

from .models import CompanyComparisonRequest, CompanyComparisonResponse


class ComparisonResponseCachePort(Protocol):
    def get(self, cache_key: str) -> CompanyComparisonResponse | None: ...

    def put(self, cache_key: str, response: CompanyComparisonResponse) -> None: ...


def normalize_question(question: str | None) -> str:
    if not question:
        return ""
    normalized = unicodedata.normalize("NFKC", question)
    return re.sub(r"\s+", " ", normalized).strip().casefold()


def comparison_cache_key(
    request: CompanyComparisonRequest,
    snapshots: tuple[BiDashboardSnapshot, ...],
    *,
    prompt_version: str,
    model: str,
) -> str:
    snapshot_lineage = sorted(
        (
            str(snapshot.company.company_id),
            str(snapshot.snapshot.snapshot_id),
            snapshot.source.workbook_hash,
        )
        for snapshot in snapshots
    )
    canonical = json.dumps(
        {
            "schema_version": 1,
            "snapshots": snapshot_lineage,
            "start_year": request.start_year,
            "end_year": request.end_year,
            "question": normalize_question(request.question),
            "prompt_version": prompt_version,
            "model": model,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class FileComparisonResponseCache:
    """Feature-local persistent cache with one validated JSON response per key."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._lock = threading.Lock()

    def get(self, cache_key: str) -> CompanyComparisonResponse | None:
        path = self._path(cache_key)
        with self._lock:
            try:
                payload = path.read_text(encoding="utf-8")
            except FileNotFoundError:
                return None
        try:
            return CompanyComparisonResponse.model_validate_json(payload)
        except (ValueError, TypeError):
            return None

    def put(self, cache_key: str, response: CompanyComparisonResponse) -> None:
        path = self._path(cache_key)
        payload = response.model_dump_json()
        with self._lock:
            self._directory.mkdir(parents=True, exist_ok=True)
            temporary = self._directory / f".{cache_key}.{uuid4().hex}.tmp"
            try:
                temporary.write_text(payload, encoding="utf-8")
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)

    def _path(self, cache_key: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{64}", cache_key):
            raise ValueError("invalid company comparison cache key")
        return self._directory / f"{cache_key}.json"


__all__ = [
    "ComparisonResponseCachePort",
    "FileComparisonResponseCache",
    "comparison_cache_key",
    "normalize_question",
]
