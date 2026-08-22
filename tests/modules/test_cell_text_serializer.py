from __future__ import annotations

from pathlib import Path
import openpyxl

from modules.structure.cell_text_serializer import (
    CellTextSerializerConfigDTO,
    CellTextSerializerModule,
    CellTextSerializerOutput,
)
from modules.structure.luna_vlm_structure_detector import SpreadsheetStructureOutput


def test_cell_text_serializer_execution(tmp_path: Path) -> None:
    wb_path = tmp_path / "test.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "IS"
    ws["B1"] = "FY2024"
    ws["C1"] = "FY2025"
    ws["A2"] = "Revenue"
    ws["B2"] = 100
    ws["C2"] = 120
    wb.save(wb_path)

    module = CellTextSerializerModule(processed_dir=tmp_path)
    current_hash = module.catalog.sha256(wb_path)

    input_dto = SpreadsheetStructureOutput.model_validate(
        {
            "file_name": "test.xlsx",
            "workbook_hash": current_hash,
            "sheet_names": ["IS"],
            "tables": [
                {
                    "sheet_name": "IS",
                    "table_index": 1,
                    "excel_range": "A1:C2",
                    "regions": [
                        {
                            "region_id": "table_1_column_header",
                            "type": "column_header",
                            "excel_range": "B1:C1",
                            "bbox_px": [0, 0, 1, 1],
                            "rows": [1, 1],
                            "columns": [2, 3],
                            "parent_ids": [],
                        },
                        {
                            "region_id": "table_1_row_header",
                            "type": "row_header",
                            "excel_range": "A2:A2",
                            "bbox_px": [0, 0, 1, 1],
                            "rows": [2, 2],
                            "columns": [1, 1],
                            "parent_ids": ["table_1_column_header"],
                        },
                        {
                            "region_id": "table_1_data",
                            "type": "data",
                            "excel_range": "B2:C2",
                            "bbox_px": [0, 0, 1, 1],
                            "rows": [2, 2],
                            "columns": [2, 3],
                            "parent_ids": [
                                "table_1_column_header",
                                "table_1_row_header",
                            ],
                        },
                    ],
                    "header_tree": [],
                }
            ],
        }
    )

    result = module.execute(input_dto, config=CellTextSerializerConfigDTO())
    validated = CellTextSerializerOutput.model_validate(result)

    assert validated.file_name == "test.xlsx"
    # Default variant_mode="both" creates 2 variants per cell (2 cells * 2 = 4 documents)
    assert len(validated.items) == 4
    assert validated.items[0].sheet_name == "IS"
    assert "Revenue" in validated.items[0].row_header
