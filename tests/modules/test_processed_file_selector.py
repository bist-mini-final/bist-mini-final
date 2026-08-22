from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from modules.common.exceptions import ModuleExecutionError
from modules.storage.processed_file_selector import (
    ProcessedFileSelectorInputDTO,
    ProcessedFileSelectorModule,
    WorkbookSelectionDTO,
)


def test_processed_file_selector_execution(tmp_path: Path):
    mock_catalog = MagicMock()
    fake_path = tmp_path / "sample.xlsx"
    fake_path.touch()

    mock_catalog.resolve.return_value = fake_path
    mock_catalog.sheet_names.return_value = ["Sheet1", "Sheet2"]
    mock_catalog.sha256.return_value = "hash_sample"

    module = ProcessedFileSelectorModule(catalog=mock_catalog)
    input_dto = ProcessedFileSelectorInputDTO(file_name="sample.xlsx", sheet_names=["Sheet1"])
    result = module.execute(input_dto)

    validated = WorkbookSelectionDTO.model_validate(result)
    assert validated.file_name == "sample.xlsx"
    assert validated.workbook_hash == "hash_sample"
    assert validated.sheet_names == ["Sheet1"]


def test_processed_file_selector_rejects_invalid_sheet(tmp_path: Path):
    mock_catalog = MagicMock()
    fake_path = tmp_path / "sample.xlsx"
    fake_path.touch()

    mock_catalog.resolve.return_value = fake_path
    mock_catalog.sheet_names.return_value = ["Sheet1"]

    module = ProcessedFileSelectorModule(catalog=mock_catalog)
    input_dto = ProcessedFileSelectorInputDTO(file_name="sample.xlsx", sheet_names=["NonExistent"])

    with pytest.raises(ModuleExecutionError):
        module.execute(input_dto)
