"""Persist workbook sheet metadata after the pgvector index exists."""

from __future__ import annotations

# ==============================================================================
# 1. Imports & Logger Setup
# ==============================================================================
import logging
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Optional, Union

from pydantic import Field

from backend.core.settings import PROCESSED_DATA_DIR
from backend.storage.spreadsheets.workbook_catalog import WorkbookCatalog
from modules.common.base_module import (
    BaseModule,
    EmptyModuleConfigDTO,
    ModuleDefinition,
    ModuleDTO,
    ModuleExecutionError,
)
from modules.common.exceptions import DocumentParsingError, StorageError
from modules.storage.pgvector_index_writer import VectorIndexDTO
from modules.storage.processed_file_selector import WorkbookSelectionDTO
from modules.structure.luna_vlm_structure_detector import SpreadsheetStructureOutput

logger = logging.getLogger(__name__)
StructureSourceDTO = Union[SpreadsheetStructureOutput, WorkbookSelectionDTO]


# ==============================================================================
# 2. DTOs & Item Models
# ==============================================================================
class SheetMetadataPersistenceInputDTO(ModuleDTO):
    """Input contract containing workbook structure and pgvector index outcome."""

    structure_input: StructureSourceDTO = Field(
        description="구조 감지 결과 또는 전수 직렬화용 워크북 선택 결과",
    )
    index_input: VectorIndexDTO = Field(
        description="source_files 저장이 완료된 pgvector 인덱스 결과",
    )


class SheetMetadataPersistenceOutputDTO(ModuleDTO):
    """Output contract containing saved sheet metadata summary."""

    sheets_saved: int = Field(description="DB에 저장된 시트 수")
    sheet_details: List[Dict[str, Any]] = Field(default_factory=list)


# ==============================================================================
# 3. Module Definition & Implementation
# ==============================================================================
_SHEET_META_DEFINITION = ModuleDefinition(
    type="sheet_metadata_persistence",
    label="Sheet Metadata Persistence",
    category="Storage / DB",
    description="pgvector 적재 후 워크북 시트 크기와 감지 테이블을 DB에 저장합니다.",
    inputs=["structure_input", "index_input"],
    outputs=["output"],
    config_fields=[],
    raw_output=True,
    cacheable=False,
    version="2",
)


class SheetMetadataPersistenceModule(BaseModule):
    """Persist sheet dimensions and detected table metadata."""

    definition: ClassVar[ModuleDefinition] = _SHEET_META_DEFINITION
    input_model = SheetMetadataPersistenceInputDTO
    config_model = EmptyModuleConfigDTO
    output_model = SheetMetadataPersistenceOutputDTO

    def __init__(
        self,
        db_manager: Any = None,
        catalog: WorkbookCatalog | None = None,
        processed_dir: Path = PROCESSED_DATA_DIR,
    ) -> None:
        """Initialize the module with an optional database manager and workbook catalog."""
        super().__init__()
        self._db_manager = db_manager
        self.catalog = catalog or WorkbookCatalog(processed_dir)

    def execute(
        self,
        input_data: SheetMetadataPersistenceInputDTO,
        config: Optional[EmptyModuleConfigDTO] = None,
    ) -> Dict[str, Any]:
        """Persist workbook sheet metadata and detected tables for the selected visible sheets."""
        from backend.storage.db_manager import DatabaseManager

        structure = input_data.structure_input
        index = input_data.index_input
        if structure.workbook_hash != index.workbook_hash:
            raise ModuleExecutionError("구조 분석과 인덱스의 workbook_hash가 다릅니다")

        database = self._db_manager or DatabaseManager()
        if not database.is_connected():
            raise StorageError("시트 메타데이터를 저장할 DB에 연결할 수 없습니다")

        workbook_path = self.catalog.resolve(structure.file_name)

        detected_tables = (
            []
            if isinstance(structure, WorkbookSelectionDTO)
            else structure.tables
        )

        if structure.sheet_names:
            visible_sheets = list(structure.sheet_names)
        elif detected_tables:
            catalog_sheets = self.catalog.sheet_names(workbook_path)
            table_sheets = {t.sheet_name for t in detected_tables}
            visible_sheets = [s for s in catalog_sheets if s in table_sheets]
        else:
            raise ModuleExecutionError(
                "저장할 시트 목록(sheet_names) 또는 감지된 테이블(tables)이 지정되지 않았습니다"
            )

        sheet_dimensions: Dict[str, tuple[int, int]] = {}
        try:
            import openpyxl

            workbook = openpyxl.load_workbook(
                workbook_path,
                read_only=True,
                data_only=True,
            )
            try:
                for sheet_name in workbook.sheetnames:
                    worksheet = workbook[sheet_name]
                    if worksheet.max_row is None or worksheet.max_column is None:
                        worksheet.calculate_dimension()
                    sheet_dimensions[sheet_name] = (
                        worksheet.max_row or 0,
                        worksheet.max_column or 0,
                    )
            finally:
                workbook.close()
        except Exception as error:
            raise DocumentParsingError(f"시트 크기 측정 실패: {error}") from error

        sheets_data: List[Dict[str, Any]] = []
        for sheet_index, sheet_name in enumerate(visible_sheets):
            if sheet_name not in sheet_dimensions:
                logger.warning("Skipping sheet '%s' not found in workbook dimensions", sheet_name)
                continue
            rows, columns = sheet_dimensions[sheet_name]
            sheet_tables = [
                table.model_dump(mode="json")
                for table in detected_tables
                if table.sheet_name == sheet_name
            ]
            sheets_data.append(
                {
                    "sheet_name": sheet_name,
                    "sheet_index": sheet_index,
                    "is_visible": True,
                    "row_count": rows,
                    "column_count": columns,
                    "detected_tables": sheet_tables,
                }
            )

        try:
            database.save_sheets(
                file_id=structure.workbook_hash,
                sheets_info=sheets_data,
            )
        except Exception as error:
            raise StorageError(f"시트 메타데이터 저장 실패: {error}") from error

        return {
            "sheets_saved": len(sheets_data),
            "sheet_details": [
                {
                    "sheet_name": sheet["sheet_name"],
                    "row_count": sheet["row_count"],
                    "column_count": sheet["column_count"],
                    "table_count": len(sheet["detected_tables"]),
                }
                for sheet in sheets_data
            ],
        }


# ==============================================================================
# 4. Exports
# ==============================================================================
__all__ = [
    "SheetMetadataPersistenceInputDTO",
    "SheetMetadataPersistenceModule",
    "SheetMetadataPersistenceOutputDTO",
]
