"""Infrastructure adapters used by data-source application services."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.storage.data_sources import IngestionJobService, IngestionRequest
from backend.storage.spreadsheets.ingestion import get_processed_file_info


class IngestionSubmissionAdapter:
    def __init__(self, service: IngestionJobService) -> None:
        self._service = service

    def submit(
        self,
        *,
        file_name: str,
        model: str,
        batch_size: int,
    ) -> dict[str, Any]:
        run = self._service.create_and_submit(
            IngestionRequest(
                file_name=file_name,
                model=model,
                batch_size=batch_size,
            )
        )
        return self._service.payload(run)


class SourceFileInspectorAdapter:
    def file_info(
        self,
        path: Path,
        *,
        workbook_hash: str | None,
    ) -> dict[str, Any]:
        return get_processed_file_info(path, workbook_hash=workbook_hash)


__all__ = ["IngestionSubmissionAdapter", "SourceFileInspectorAdapter"]
