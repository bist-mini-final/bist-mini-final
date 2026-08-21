from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, cast

from pydantic import BaseModel, Field

from ..core.settings import PROCESSED_DATA_DIR
from ..spreadsheets.workbook_catalog import WorkbookCatalog, WorkbookCatalogError
from .base import (
    EmptyModuleConfigDTO,
    ExecutableModule,
    ModuleDefinition,
    ModuleExecutionError,
    ModuleInputDTO,
    ModuleDTO,
)


class ProcessedFileSelectorInputDTO(ModuleInputDTO):
    file_name: str = Field(
        min_length=1,
        description="data/processed에서 선택할 Excel 파일명",
    )


class WorkbookSelectionDTO(ModuleDTO):
    file_name: str = Field(description="선택된 processed Excel 파일명")
    workbook_hash: str = Field(description="파일 변경을 식별하는 SHA-256")
    sheet_names: List[str] = Field(
        min_length=1,
        description="내부·빈 시트를 제외한 처리 대상 시트명",
    )


class ProcessedFileSelectorModule(ExecutableModule):
    definition = ModuleDefinition(
        type="processed_file_selector",
        label="Processed Excel File Selector",
        category="Source",
        description="data/processed의 Excel 파일 하나를 안전하게 선택합니다.",
        inputs=[],
        outputs=["output"],
        config_fields=[],
        raw_output=True,
        cacheable=False,
        version="2",
    )
    input_model = ProcessedFileSelectorInputDTO
    config_model = EmptyModuleConfigDTO
    execution_model = ProcessedFileSelectorInputDTO
    output_model = WorkbookSelectionDTO

    def __init__(
        self,
        catalog: WorkbookCatalog | None = None,
        processed_dir: Path = PROCESSED_DATA_DIR,
    ) -> None:
        self.catalog = catalog or WorkbookCatalog(processed_dir)

    def contract(self) -> Dict[str, Any]:
        contract = super().contract()
        available = self.catalog.file_names()
        file_schema = contract["input_schema"]["properties"]["file_name"]
        file_schema["enum"] = available
        if available:
            file_schema["default"] = available[0]
        return contract

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        input_data = cast(ProcessedFileSelectorInputDTO, payload)
        try:
            path = self.catalog.resolve(input_data.file_name)
            sheet_names = self.catalog.sheet_names(path)
        except (OSError, ValueError, WorkbookCatalogError) as error:
            raise ModuleExecutionError(str(error)) from error
        if not sheet_names:
            raise ModuleExecutionError("선택한 Excel 파일에 처리할 시트가 없습니다")
        return {
            "file_name": path.name,
            "workbook_hash": self.catalog.sha256(path),
            "sheet_names": sheet_names,
        }
