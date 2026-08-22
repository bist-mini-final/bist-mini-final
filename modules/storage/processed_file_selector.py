"""데이터 소스 디렉터리(`data/source_files`)의 엑셀 파일을 선택하고 대상 시트 목록을 검증하는 모듈.

저장된 Excel 통합 문서를 분석하여 SHA-256 해시를 산출하고,
숨김 시트나 빈 시트를 제외한 실제 처리 대상 시트명 목록을 포함한 WorkbookSelectionDTO를 생성합니다.

Example:
    Input DTO (입력 예시):
    ```json
    {
      "file_name": "samsung_electronics_2023.xlsx",
      "sheet_names": ["손익계산서", "재무상태표"]
    }
    ```

    Output DTO (출력 예시):
    ```json
    {
      "file_name": "samsung_electronics_2023.xlsx",
      "workbook_hash": "a1b2c3d4e5f67890abcdef1234567890abcdef1234567890abcdef1234567890",
      "sheet_names": ["손익계산서", "재무상태표"]
    }
    ```
"""

from __future__ import annotations

# ==============================================================================
# 1. Imports & Logger Setup
# ==============================================================================
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import Field

from backend.core.settings import PROCESSED_DATA_DIR
from backend.storage.spreadsheets.workbook_catalog import WorkbookCatalog
from modules.common.base_module import (
    BaseModule,
    EmptyModuleConfigDTO,
    ModuleDefinition,
    ModuleDTO,
    ModuleExecutionError,
    ModuleInputDTO,
)

logger = logging.getLogger(__name__)


# ==============================================================================
# 3. DTOs & Item Models
# ==============================================================================
class ProcessedFileSelectorInputDTO(ModuleInputDTO):
    """Excel 파일 선택 입력 DTO 계약."""

    file_name: str = Field(
        min_length=1,
        description="data/source_files에서 선택할 Excel 파일명",
    )
    sheet_names: Optional[List[str]] = Field(
        default=None,
        description="처리할 표시 시트 목록. 생략하면 모든 표시 시트를 선택합니다.",
    )


class WorkbookSelectionDTO(ModuleDTO):
    """선택된 통합 문서 및 시트 메타데이터 DTO."""

    file_name: str = Field(description="선택된 source Excel 파일명")
    workbook_hash: str = Field(description="파일 변경을 식별하는 SHA-256")
    sheet_names: List[str] = Field(
        min_length=1,
        description="내부·빈 시트를 제외한 처리 대상 시트명",
    )


# ==============================================================================
# 4. Module Implementation
# ==============================================================================
class ProcessedFileSelectorModule(BaseModule):
    """Excel 파일 및 대상 시트 선택 모듈.

    `data/source_files` 디렉터리의 엑셀 파일을 조회하고 유효한 시트들을 필터링하여 해시 메타데이터와 함께 전달합니다.

    Input:
        - `file_name` (`str`): 분석할 엑셀 파일명
        - `sheet_names` (`Optional[List[str]]`): 처리할 특정 시트명 목록 (선택)

    Output:
        - `file_name` (`str`): 확인된 엑셀 파일명
        - `workbook_hash` (`str`): 파일 SHA-256 해시값
        - `sheet_names` (`List[str]`): 최종 확정된 처리 대상 시트명 리스트
    """

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

    def execute(
        self,
        input_data: ProcessedFileSelectorInputDTO,
        config: Optional[EmptyModuleConfigDTO] = None,
    ) -> Dict[str, Any]:
        path = self.catalog.resolve(input_data.file_name)
        available_sheet_names = self.catalog.sheet_names(path)
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


# ==============================================================================
# 5. Exports
# ==============================================================================
__all__ = [
    "ProcessedFileSelectorInputDTO",
    "ProcessedFileSelectorModule",
    "WorkbookSelectionDTO",
]
