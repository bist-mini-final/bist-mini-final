"""Capabilities required by data-source application and presentation services."""

from __future__ import annotations

from collections.abc import AsyncIterable, Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from backend.domains.workflow.domain.models import (
    WorkflowDocument,
    WorkflowExecutionRequest,
    WorkflowRun,
)


class IngestionWorkflowRepository(Protocol):
    def load(self, workflow_id: str) -> WorkflowDocument: ...


class IngestionRunRepository(Protocol):
    def load(self, run_id: str) -> WorkflowRun: ...

    def load_summary(self, run_id: str) -> WorkflowRun: ...

    def list_summaries(
        self,
        workflow_id: str | None = None,
        limit: int | None = None,
    ) -> list[WorkflowRun]: ...

    def delete(self, run_id: str) -> bool: ...

    def find_ingestion_run_id_by_index(self, index_id: str) -> str | None: ...


class IngestionWorkflowExecutor(Protocol):
    def create_run(
        self,
        workflow: WorkflowDocument,
        request: WorkflowExecutionRequest,
    ) -> WorkflowRun: ...


class DataSourceCatalogPort(Protocol):
    def list_files(self, processed_dir: Path) -> list[dict[str, Any]]: ...

    def preview_file(
        self,
        processed_dir: Path,
        filename: str,
        *,
        sheet_name: str | None,
        max_rows: int,
    ) -> dict[str, Any]: ...

    def list_indexes(self) -> list[dict[str, Any]]: ...

    def get_index(self, index_id: str) -> dict[str, Any] | None: ...

    def update_index_company(self, index_id: str, company_name: str) -> bool: ...

    def delete_index(self, index_id: str) -> bool: ...

    def search_index(
        self,
        index_id: str,
        query: str,
        limit: int,
    ) -> list[dict[str, Any]]: ...


class DataSourceDatabasePort(Protocol):
    def current_info(self) -> dict[str, Any]: ...

    def inspect(self, database_url: str) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class StoredSourceFile:
    file_name: str
    path: Path
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class DeletedSourceFile:
    file_name: str
    sha256: str | None


class SourceFileStorageLimitExceeded(Exception):
    """Raised when an upload exceeds the application-provided byte limit."""


class SourceFileStoragePort(Protocol):
    async def save(
        self,
        file_name: str,
        chunks: AsyncIterable[bytes],
        *,
        max_size_bytes: int,
    ) -> StoredSourceFile: ...

    def delete(
        self,
        file_name: str,
        *,
        hash_suffixes: Collection[str],
    ) -> DeletedSourceFile: ...

    def resolve_existing(self, file_name: str) -> Path | None: ...


__all__ = [
    "DataSourceCatalogPort",
    "DataSourceDatabasePort",
    "DeletedSourceFile",
    "IngestionRunRepository",
    "IngestionWorkflowExecutor",
    "IngestionWorkflowRepository",
    "SourceFileStorageLimitExceeded",
    "SourceFileStoragePort",
    "StoredSourceFile",
]
