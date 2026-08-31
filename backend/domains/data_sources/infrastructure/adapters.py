"""Infrastructure adapters used by data-source application services."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.domains.data_sources.application.ingestion_jobs import (
    IngestionJobService,
    IngestionRequest,
)
from backend.domains.data_sources.infrastructure.spreadsheets.ingestion import (
    delete_vector_index,
    get_processed_file_info,
    get_vector_index_detail,
    list_processed_files,
    list_vector_indexes,
    preview_excel_sheet,
    search_vector_index,
)
from backend.shared.application.embeddings import EmbeddingEncoder


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


class SpreadsheetVectorCatalogAdapter:
    """Expose spreadsheet/vector queries behind one data-source capability."""

    def __init__(self, vector_store: Any, embeddings: EmbeddingEncoder) -> None:
        self._vectors = vector_store
        self._embeddings = embeddings

    def list_files(self, processed_dir: Path) -> list[dict[str, Any]]:
        return list_processed_files(processed_dir, self._vectors)

    def preview_file(
        self,
        processed_dir: Path,
        filename: str,
        *,
        sheet_name: str | None,
        max_rows: int,
    ) -> dict[str, Any]:
        return preview_excel_sheet(
            filename,
            sheet_name=sheet_name,
            max_rows=max_rows,
            processed_dir=processed_dir,
        )

    def list_indexes(self) -> list[dict[str, Any]]:
        return list_vector_indexes(self._vectors)

    def get_index(self, index_id: str) -> dict[str, Any] | None:
        return get_vector_index_detail(index_id, pgvector_store=self._vectors)

    def update_index_company(self, index_id: str, company_name: str) -> bool:
        return bool(self._vectors.update_index_company(index_id, company_name))

    def delete_index(self, index_id: str) -> bool:
        return delete_vector_index(index_id, pgvector_store=self._vectors)

    def search_index(
        self,
        index_id: str,
        query: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        return search_vector_index(
            index_id=index_id,
            query_text=query,
            pgvector_store=self._vectors,
            embedding_encoder=self._embeddings,
            limit=limit,
        )


class PgVectorDatabaseAdapter:
    """Combine current-store health and explicit connection inspection."""

    def __init__(self, vector_store: Any, connection_probe: Any) -> None:
        self._vectors = vector_store
        self._probe = connection_probe

    def current_info(self) -> dict[str, Any]:
        return self._vectors.get_db_info()

    def inspect(self, database_url: str) -> dict[str, Any]:
        return self._probe.inspect(database_url)


__all__ = [
    "IngestionSubmissionAdapter",
    "PgVectorDatabaseAdapter",
    "SourceFileInspectorAdapter",
    "SpreadsheetVectorCatalogAdapter",
]
