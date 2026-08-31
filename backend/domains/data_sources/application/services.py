"""Process-neutral service bundle consumed by data-source presentation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .files import DataSourceFileService
from .ingestion_jobs import IngestionJobService
from .ports import (
    DataSourceCatalogPort,
    DataSourceDatabasePort,
    IngestionRunRepository,
    SourceFileStoragePort,
)


@dataclass(frozen=True, slots=True)
class DataSourceApiServices:
    processed_dir: Path
    configured_database_url: str
    file_storage: SourceFileStoragePort
    files: DataSourceFileService
    ingestion: IngestionJobService
    runs: IngestionRunRepository
    catalog: DataSourceCatalogPort
    database: DataSourceDatabasePort


__all__ = ["DataSourceApiServices"]
