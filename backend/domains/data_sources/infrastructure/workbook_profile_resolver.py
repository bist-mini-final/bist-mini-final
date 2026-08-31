"""Resolve or rebuild workbook profiles for already indexed source files."""

from __future__ import annotations

from pathlib import Path

from backend.core.settings import PROCESSED_DATA_DIR
from backend.domains.data_sources.domain.workbook_profiles import WorkbookProfile
from backend.domains.data_sources.infrastructure.postgres.source_files import (
    PostgresSourceFileRepository,
)
from backend.domains.data_sources.infrastructure.postgres.workbook_profiles import (
    PostgresWorkbookProfileRepository,
)
from backend.domains.data_sources.infrastructure.spreadsheets.workbook_catalog import (
    WorkbookCatalog,
)
from backend.domains.data_sources.infrastructure.spreadsheets.workbook_profile_extractor import (
    WORKBOOK_PROFILE_VERSION,
    WorkbookProfileExtractor,
)
from modules.structure.luna_vlm_structure_detector import (
    ClassifiedTableDTO,
    SpreadsheetStructureOutput,
)


class StoredWorkbookProfileResolver:
    """Backfill a deterministic profile from the original workbook on demand."""

    def __init__(
        self,
        database_url: str,
        processed_dir: Path = PROCESSED_DATA_DIR,
    ) -> None:
        self._profiles = PostgresWorkbookProfileRepository(database_url)
        self._source_files = PostgresSourceFileRepository(database_url)
        self._catalog = WorkbookCatalog(processed_dir)
        self._extractor = WorkbookProfileExtractor()

    def resolve(
        self,
        *,
        file_name: str,
        workbook_hash: str,
        index_id: str,
        force: bool = False,
    ) -> WorkbookProfile:
        existing = self._profiles.get(
            workbook_hash=workbook_hash,
            index_id=index_id,
            profile_version=WORKBOOK_PROFILE_VERSION,
        )
        if not force and existing is not None and existing.is_financially_complete:
            return existing
        workbook_path = self._catalog.resolve(file_name)
        if self._catalog.sha256(workbook_path) != workbook_hash:
            raise ValueError("원본 워크북의 hash가 인덱스 lineage와 다릅니다")
        sheet_records = self._source_files.list_sheets(workbook_hash)
        tables = tuple(
            table
            for sheet in sheet_records
            for raw_table in sheet.get("detected_tables", [])
            if (table := self._validated_table(raw_table)) is not None
        )
        structure = SpreadsheetStructureOutput(
            file_name=file_name,
            workbook_hash=workbook_hash,
            sheet_names=[
                str(sheet["sheet_name"])
                for sheet in sheet_records
                if sheet.get("is_visible", True)
            ],
            tables=list(tables),
        )
        return self._profiles.save(
            self._extractor.extract(
                workbook_path=workbook_path,
                structure=structure,
                index_id=index_id,
            )
        )

    @staticmethod
    def _validated_table(raw_table: object) -> ClassifiedTableDTO | None:
        try:
            return ClassifiedTableDTO.model_validate(raw_table)
        except (TypeError, ValueError):
            return None


__all__ = ["StoredWorkbookProfileResolver"]
