from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import openpyxl
import pytest

from backend.domains.data_sources.infrastructure.spreadsheets.workbook_catalog import (
    WorkbookCatalog,
)
from modules.common.exceptions import ModuleExecutionError
from modules.storage.pgvector_index_writer import VectorIndexDTO
from modules.storage.processed_file_selector import WorkbookSelectionDTO
from modules.storage.sheet_metadata_persistence import (
    SheetMetadataPersistenceInputDTO,
    SheetMetadataPersistenceModule,
)


def test_sheet_metadata_persistence_execution(tmp_path: Path):
    wb_path = tmp_path / "test.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Sheet1"
    ws["A1"] = "Data"
    wb.save(wb_path)

    mock_db = MagicMock()
    mock_db.is_connected.return_value = True

    module = SheetMetadataPersistenceModule(
        db_manager=mock_db,
        catalog=WorkbookCatalog(tmp_path),
    )
    input_dto = SheetMetadataPersistenceInputDTO(
        structure_input=WorkbookSelectionDTO(
            file_name="test.xlsx",
            workbook_hash="hash_123",
            sheet_names=["Sheet1"],
        ),
        index_input=VectorIndexDTO(
            index_id="idx_" + ("1" * 64),
            file_name="test.xlsx",
            workbook_hash="hash_123",
            model="text-embedding-3-large",
            dimension=3072,
            document_count=10,
        ),
    )

    result = module.execute(input_dto)
    assert result["sheets_saved"] == 1
    assert mock_db.save_sheets.called


def test_sheet_metadata_persistence_hash_mismatch(tmp_path: Path):
    mock_db = MagicMock()
    module = SheetMetadataPersistenceModule(
        db_manager=mock_db,
        catalog=WorkbookCatalog(tmp_path),
    )

    input_dto = SheetMetadataPersistenceInputDTO(
        structure_input=WorkbookSelectionDTO(
            file_name="test.xlsx",
            workbook_hash="hash_1",
            sheet_names=["Sheet1"],
        ),
        index_input=VectorIndexDTO(
            index_id="idx_" + ("1" * 64),
            file_name="test.xlsx",
            workbook_hash="hash_2",
            model="text-embedding-3-large",
            dimension=3072,
            document_count=10,
        ),
    )

    with pytest.raises(ModuleExecutionError):
        module.execute(input_dto)
