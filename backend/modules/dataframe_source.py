"""
DataFrame Source
────────────────
코드 실행 기반 RAG(Code Execution RAG) 시연용 Source 모듈.

data/processed/ 아래의 Excel 파일을 pandas DataFrame으로 읽어
시트별 메타데이터와 스키마(컬럼명 / 데이터 타입 / 샘플 행)를 출력합니다.
LLM Code Agent가 pandas 코드 생성 시 참조할 DataFrame 컨텍스트를 제공합니다.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

from pydantic import BaseModel, Field

from ..config import PROCESSED_DATA_DIR
from ..spreadsheets.workbook_catalog import WorkbookCatalog, WorkbookCatalogError
from .base import (
    ExecutableModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleDTO,
    ModuleExecutionError,
    ModuleInputDTO,
)


class DataframeSourceInputDTO(ModuleInputDTO):
    file_name: str = Field(
        min_length=1,
        description="data/processed에서 선택할 Excel 파일명",
    )


class DataframeSourceConfigDTO(ModuleConfigDTO):
    sample_rows: int = Field(
        default=3,
        ge=0,
        le=10,
        description="각 시트에서 추출할 샘플 행 수 (0이면 스키마만)",
    )
    max_sheets: int = Field(
        default=5,
        ge=1,
        le=20,
        description="출력에 포함할 최대 시트 수",
    )


class DataframeSourceExecutionDTO(DataframeSourceInputDTO, DataframeSourceConfigDTO):
    """Internal union of source identity and preview policy."""


class SheetSchemaDTO(ModuleDTO):
    sheet_name: str
    row_count: int
    column_count: int
    columns: List[str]
    dtypes: Dict[str, str]
    sample: List[Dict[str, Any]]


class DataframeSourceOutput(ModuleDTO):
    file_name: str
    workbook_hash: str
    total_sheets: int
    sheets: List[SheetSchemaDTO]
    variable_hint: str = Field(
        description="LLM 코드 에이전트에 전달할 DataFrame 변수명 힌트"
    )


class DataframeSourceModule(ExecutableModule):
    definition = ModuleDefinition(
        type="dataframe_source",
        label="DataFrame Source (Code RAG)",
        category="Source",
        description=(
            "Excel 파일을 pandas DataFrame으로 읽어 시트별 스키마와 샘플을 출력합니다. "
            "LLM Code Agent가 pandas 코드를 작성할 때 참조할 DataFrame 컨텍스트를 제공합니다. "
            "(Code Execution RAG 시연용)"
        ),
        inputs=[],
        outputs=["output"],
        config_fields=["sample_rows", "max_sheets"],
        raw_output=True,
        version="1",
    )
    input_model = DataframeSourceInputDTO
    config_model = DataframeSourceConfigDTO
    execution_model = DataframeSourceExecutionDTO
    output_model = DataframeSourceOutput

    def __init__(self, processed_dir: Path = PROCESSED_DATA_DIR) -> None:
        self.catalog = WorkbookCatalog(processed_dir)
        self.processed_dir = processed_dir

    def contract(self) -> Dict[str, Any]:
        contract = super().contract()
        available = self.catalog.file_names()
        file_schema = contract["input_schema"]["properties"]["file_name"]
        file_schema["enum"] = available
        if available:
            file_schema["default"] = available[0]
        return contract

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        try:
            import pandas as pd
        except ImportError as err:
            raise ModuleExecutionError(
                "pandas가 설치되어 있지 않습니다: pip install pandas openpyxl"
            ) from err

        input_data = cast(DataframeSourceExecutionDTO, payload)

        try:
            path = self.catalog.resolve(input_data.file_name)
        except (OSError, ValueError, WorkbookCatalogError) as err:
            raise ModuleExecutionError(str(err)) from err

        workbook_hash = hashlib.sha256(path.read_bytes()).hexdigest()[:16]

        try:
            xl = pd.ExcelFile(path, engine="openpyxl")
            all_sheets = xl.sheet_names
        except Exception as err:
            raise ModuleExecutionError(f"Excel 파일 로드 실패: {err}") from err

        sheets_out: List[Dict[str, Any]] = []
        target_sheets = all_sheets[: input_data.max_sheets]

        for sheet_name in target_sheets:
            try:
                df = xl.parse(sheet_name, header=0)
                # Drop completely empty columns/rows
                df = df.dropna(how="all", axis=1).dropna(how="all", axis=0)
                columns = [str(c) for c in df.columns.tolist()]
                dtypes = {str(k): str(v) for k, v in df.dtypes.to_dict().items()}
                sample_df = df.head(input_data.sample_rows)
                sample = [
                    {str(k): (None if pd.isna(v) else v)
                     for k, v in row.items()}
                    for row in sample_df.to_dict(orient="records")
                ]
                sheets_out.append(
                    SheetSchemaDTO(
                        sheet_name=sheet_name,
                        row_count=len(df),
                        column_count=len(df.columns),
                        columns=columns,
                        dtypes=dtypes,
                        sample=sample,
                    ).model_dump()
                )
            except Exception:
                continue

        stem = path.stem.replace(" ", "_").replace("-", "_")
        variable_hint = f"dfs['{stem}']"

        return {
            "file_name": path.name,
            "workbook_hash": workbook_hash,
            "total_sheets": len(all_sheets),
            "sheets": sheets_out,
            "variable_hint": variable_hint,
        }
