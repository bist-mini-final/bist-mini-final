from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import openpyxl

from backend.domains.data_sources.infrastructure.spreadsheets.workbook_catalog import (
    WorkbookCatalog,
)


def _remove_worksheet_dimension(path: Path) -> None:
    rewritten_path = path.with_suffix(".rewritten.xlsx")
    with ZipFile(path, "r") as source, ZipFile(
        rewritten_path,
        "w",
        compression=ZIP_DEFLATED,
    ) as target:
        for item in source.infolist():
            payload = source.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                start = payload.find(b"<dimension")
                end = payload.find(b"/>", start)
                assert start >= 0 and end >= 0
                payload = payload[:start] + payload[end + 2 :]
            target.writestr(item, payload)
    rewritten_path.replace(path)


def test_sheet_names_supports_workbooks_without_dimension_metadata(
    tmp_path: Path,
) -> None:
    workbook_path = tmp_path / "unsized.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "Financials"
    sheet.append(["Metric", "FY2025"])
    sheet.append(["Revenue", 120])
    workbook.save(workbook_path)
    workbook.close()
    _remove_worksheet_dimension(workbook_path)

    assert WorkbookCatalog.sheet_names(workbook_path) == ["Financials"]
