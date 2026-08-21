from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, cast

from pydantic import BaseModel, Field

from backend.core.settings import PROCESSED_DATA_DIR
from backend.storage.spreadsheets.workbook_catalog import WorkbookCatalog, WorkbookCatalogError
from modules.common.base_module import (
    EmptyModuleConfigDTO,
    BaseModule,
    ModuleDefinition,
    ModuleExecutionError,
    ModuleInputDTO,
    ModuleDTO,
)


class ProcessedFileSelectorInputDTO(ModuleInputDTO):
    file_name: str = Field(
        min_length=1,
        description="data/source_files에서 선택할 Excel 파일명",
    )
    sheet_names: Optional[List[str]] = Field(
        default=None,
        description="처리할 표시 시트 목록. 생략하면 모든 표시 시트를 선택합니다.",
    )


class WorkbookSelectionDTO(ModuleDTO):
    file_name: str = Field(description="선택된 source Excel 파일명")
    workbook_hash: str = Field(description="파일 변경을 식별하는 SHA-256")
    sheet_names: List[str] = Field(
        min_length=1,
        description="내부·빈 시트를 제외한 처리 대상 시트명",
    )


class ProcessedFileSelectorModule(BaseModule):
    definition = ModuleDefinition(
        type="processed_file_selector",
        label="Processed Excel File Selector",
        category="Source",
        description="data/source_files의 Excel 파일 하나를 안전하게 선택합니다.",
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
        """
        Resolve the requested processed workbook and select its processing sheets.
        
        Parameters:
            payload (BaseModel): Input containing the processed workbook filename and
                optionally the sheet names to select.
        
        Returns:
            Dict[str, Any]: The resolved filename, workbook SHA-256 hash, and selected
                sheet names in catalog order.
        
        Raises:
            ModuleExecutionError: If the workbook cannot be resolved, a requested sheet
                does not exist, or no processing sheets are selected.
        """
        input_data = cast(ProcessedFileSelectorInputDTO, payload)
        try:
            path = self.catalog.resolve(input_data.file_name)
            available_sheet_names = self.catalog.sheet_names(path)
        except (OSError, ValueError, WorkbookCatalogError) as error:
            raise ModuleExecutionError(str(error)) from error
        requested_sheet_names = input_data.sheet_names
        if requested_sheet_names is None:
            sheet_names = available_sheet_names
        else:
            unknown_sheet_names = sorted(
                set(requested_sheet_names) - set(available_sheet_names)
            )
            if unknown_sheet_names:
                raise ModuleExecutionError(
                    "Excel 파일에 없는 시트가 선택되었습니다: "
                    + ", ".join(unknown_sheet_names)
                )
            requested = set(requested_sheet_names)
            sheet_names = [
                name for name in available_sheet_names if name in requested
            ]
        if not sheet_names:
            raise ModuleExecutionError("선택한 Excel 파일에 처리할 시트가 없습니다")
        return {
            "file_name": path.name,
            "workbook_hash": self.catalog.sha256(path),
            "sheet_names": sheet_names,
        }
