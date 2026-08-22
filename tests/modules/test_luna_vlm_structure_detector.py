from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
import openpyxl

from backend.storage.spreadsheets.workbook_catalog import WorkbookCatalog
from modules.structure.luna_vlm_structure_detector import (
    LunaVlmStructureDetectorConfigDTO,
    LunaVlmStructureDetectorModule,
    SpreadsheetStructureOutput,
)


def test_luna_detector_executes_on_tiny_workbook(tmp_path: Path) -> None:
    workbook_path = tmp_path / "tiny.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws["A1"] = "Category"
    ws["B1"] = "2023"
    ws["A2"] = "Revenue"
    ws["B2"] = 1000
    wb.save(workbook_path)

    catalog = WorkbookCatalog(tmp_path)
    vision_client = MagicMock()
    vision_client.complete_structured.return_value = (
        '{"tables":[{"excel_range":"A1:B2","title_range":null,'
        '"column_header_range":"B1:B1","row_header_range":"A2:A2",'
        '"data_range":"B2:B2"}]}'
    )

    module = LunaVlmStructureDetectorModule(
        vision_client=vision_client,
        catalog=catalog,
        processed_dir=tmp_path,
        artifact_dir=tmp_path / "luna",
    )

    input_data = {
        "file_name": workbook_path.name,
        "workbook_hash": catalog.sha256(workbook_path),
        "sheet_names": ["Sheet1"],
    }

    result = module.run(
        input_data,
        LunaVlmStructureDetectorConfigDTO(validation_retries=0, max_concurrency=1),
    )
    validated = SpreadsheetStructureOutput.model_validate(result)

    assert len(validated.tables) == 1
    assert validated.tables[0].sheet_name == "Sheet1"
