from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Any, Callable, Dict, Iterable, List, Literal, Optional, Sequence, cast

import openpyxl
from openpyxl.cell.cell import MergedCell
from openpyxl.utils import get_column_letter
from pydantic import BaseModel, Field

from backend.core.settings import PROCESSED_DATA_DIR
from backend.storage.spreadsheets.cell_visibility import WorksheetVisibility, worksheet_visible
from backend.storage.spreadsheets.structured_cell_text import (
    SERIALIZATION_VERSION,
    UNKNOWN_FIELD,
    WorksheetValueReader,
    canonical_sheet_name,
    ensure_period_header,
    format_cell_value,
    generate_header_combinations,
    serialize_structured_cell,
    sheet_code,
)
from backend.storage.spreadsheets.workbook_catalog import WorkbookCatalog, WorkbookCatalogError
from modules.common.base_module import (
    BaseModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleDTO,
    ModuleExecutionError,
)
from modules.storage.processed_file_selector import WorkbookSelectionDTO
from modules.structure.spreadsheet_structure import (
    ClassifiedRegionDTO,
    ClassifiedTableDTO,
    SpreadsheetStructureOutput,
)


class CellTextSerializerInputDTO(SpreadsheetStructureOutput):
    """Classified workbook data received from a structure detector."""


class CellTextSerializerConfigDTO(ModuleConfigDTO):
    variant_mode: Literal["header_only", "header_with_value", "both"] = Field(
        default="both",
        description="생성할 검색 문서 변형 (header_only, header_with_value, 또는 both)",
        json_schema_extra={
            "enum": ["header_only", "header_with_value", "both"],
            "options": ["header_only", "header_with_value", "both"],
        },
    )


class CellTextSerializerExecutionDTO(
    CellTextSerializerInputDTO,
    CellTextSerializerConfigDTO,
):
    """Combined input and config DTO for execution."""


class CellTextDocumentDTO(ModuleDTO):
    cell_id: str = Field(description="시트 코드와 셀 좌표로 만든 검색 문서 ID")
    sheet_name: str = Field(description="정규화된 원본 시트 이름")
    cell_coord: str = Field(description="Excel 셀 좌표")
    row_header: List[str] = Field(description="상위 수준부터 수집한 행 헤더")
    column_header: List[str] = Field(description="상위 수준부터 수집한 열 헤더")
    cell_value: str = Field(description="Excel 데이터 셀의 표시 값")
    variant: Literal["header_only", "header_with_value"]
    text: str = Field(description="4필드 공통 포맷으로 직렬화한 검색 문서")


class CellTextSerializerOutput(ModuleDTO):
    file_name: str
    workbook_hash: str
    items: List[CellTextDocumentDTO]


class CellTextSerializerModule(BaseModule):
    definition = ModuleDefinition(
        type="cell_text_serializer",
        label="Structured Cell Text Serializer",
        category="Transform",
        description="분류된 Excel 셀을 Sheet·Row Header·Column Header·Cell Value 포맷으로 직렬화합니다.",
        inputs=["input"],
        outputs=["output"],
        config_fields=["variant_mode"],
        raw_output=True,
        version=SERIALIZATION_VERSION,
    )
    input_model = CellTextSerializerInputDTO
    config_model = CellTextSerializerConfigDTO
    execution_model = CellTextSerializerExecutionDTO
    output_model = CellTextSerializerOutput

    def __init__(
        self,
        catalog: WorkbookCatalog | None = None,
        processed_dir: Path = PROCESSED_DATA_DIR,
    ) -> None:
        self.catalog = catalog or WorkbookCatalog(processed_dir)

    @staticmethod
    def _region(
        table: ClassifiedTableDTO,
        region_type: str,
    ) -> Optional[ClassifiedRegionDTO]:
        return next(
            (region for region in table.regions if region.type == region_type),
            None,
        )

    @staticmethod
    def _header_values(
        reader: WorksheetValueReader,
        row: int,
        column: int,
        title_region: Optional[ClassifiedRegionDTO],
        row_region: Optional[ClassifiedRegionDTO],
        column_region: Optional[ClassifiedRegionDTO],
    ) -> tuple[List[str], List[str]]:
        row_headers: List[str] = []
        if title_region is not None:
            for title_row in range(title_region.rows[0], title_region.rows[1] + 1):
                if reader.row_hidden(title_row):
                    continue
                for title_column in range(
                    title_region.columns[0],
                    title_region.columns[1] + 1,
                ):
                    if reader.column_hidden(title_column):
                        continue
                    value = reader.value(title_row, title_column)
                    if value is not None and value not in row_headers:
                        row_headers.append(value)
        if row_region is not None:
            for header_column in range(
                row_region.columns[0],
                row_region.columns[1] + 1,
            ):
                if reader.column_hidden(header_column):
                    continue
                value = reader.value(row, header_column)
                if value is not None and value not in row_headers:
                    row_headers.append(value)

        column_headers: List[str] = []
        if column_region is not None:
            for header_row in range(
                column_region.rows[0],
                column_region.rows[1] + 1,
            ):
                if reader.row_hidden(header_row):
                    continue
                value = reader.value(header_row, column)
                if value is not None:
                    column_headers.append(value)
        return row_headers, ensure_period_header(column_headers)

    def _table_documents(
        self,
        reader: WorksheetValueReader,
        table: ClassifiedTableDTO,
        seen_cell_ids: set[str],
        variant_mode: str = "both",
    ) -> List[Dict[str, Any]]:
        """
        Generate serialized documents for the visible, non-empty cells in a classified table.
        
        Parameters:
            reader (WorksheetValueReader): Provides worksheet values and visibility information.
            table (ClassifiedTableDTO): Classified table whose data cells and headers are serialized.
            seen_cell_ids (set[str]): Cell identifiers already generated by other tables.
            variant_mode (str): Document variants to generate: ``"header_only"``,
                ``"header_with_value"``, or ``"both"``.
        
        Returns:
            List[Dict[str, Any]]: Serialized cell documents.
        
        Raises:
            ModuleExecutionError: If a cell identifier is generated more than once across tables.
        """
        data_region = self._region(table, "data")
        if data_region is None:
            return []
        row_region = self._region(table, "row_header")
        column_region = self._region(table, "column_header")
        title_region = self._region(table, "title")
        canonical_name = canonical_sheet_name(table.sheet_name)
        code = sheet_code(table.sheet_name)
        documents: List[Dict[str, Any]] = []

        for row in range(data_region.rows[0], data_region.rows[1] + 1):
            if reader.row_hidden(row):
                continue
            for column in range(
                data_region.columns[0],
                data_region.columns[1] + 1,
            ):
                if reader.column_hidden(column):
                    continue
                cell_value = reader.value(row, column)
                if cell_value is None:
                    continue
                row_headers, column_headers = self._header_values(
                    reader,
                    row,
                    column,
                    title_region,
                    row_region,
                    column_region,
                )
                if not row_headers:
                    continue

                cell_coord = f"{get_column_letter(column)}{row}"
                cell_id = f"{code} Cell {cell_coord}"
                if cell_id in seen_cell_ids:
                    raise ModuleExecutionError(
                        f"겹치는 테이블 영역에서 중복 셀이 생성되었습니다: {cell_id}"
                    )
                seen_cell_ids.add(cell_id)

                cell_seen_texts: set[str] = set()
                header_combos = generate_header_combinations(row_headers, column_headers)
                for r_combo, c_combo in header_combos:
                    common = {
                        "cell_id": cell_id,
                        "sheet_name": canonical_name,
                        "cell_coord": cell_coord,
                        "row_header": r_combo,
                        "column_header": c_combo,
                        "cell_value": cell_value,
                    }
                    if variant_mode == "both":
                        active_variants = [("header_only", UNKNOWN_FIELD), ("header_with_value", cell_value)]
                    elif variant_mode == "header_with_value":
                        active_variants = [("header_with_value", cell_value)]
                    else:
                        active_variants = [("header_only", UNKNOWN_FIELD)]

                    for variant, val in active_variants:
                        text = serialize_structured_cell(
                            canonical_name,
                            r_combo,
                            c_combo,
                            val,
                        )
                        if text not in cell_seen_texts:
                            cell_seen_texts.add(text)
                            documents.append(
                                {
                                    **common,
                                    "variant": variant,
                                    "text": text,
                                }
                            )
        return documents

    def execute(
        self,
        input_data: CellTextSerializerInputDTO,
        config: Optional[CellTextSerializerConfigDTO] = None,
    ) -> Dict[str, Any]:
        """
        Serialize classified workbook cells into cell-text documents.
        
        Parameters:
            payload (BaseModel): Classification data and serialization configuration.
        
        Returns:
            Dict[str, Any]: Workbook filename, SHA-256 hash, and serialized cell documents.
        
        Raises:
            ModuleExecutionError: If the workbook cannot be resolved or read, has changed since classification, or references a missing or hidden sheet.
        """
        if config is None and isinstance(input_data, CellTextSerializerExecutionDTO):
            cfg = input_data
        else:
            cfg = config or CellTextSerializerConfigDTO()
        try:
            workbook_path = self.catalog.resolve(input_data.file_name)
            current_hash = self.catalog.sha256(workbook_path)
        except (OSError, ValueError, WorkbookCatalogError) as error:
            raise ModuleExecutionError(str(error)) from error
        if current_hash != input_data.workbook_hash:
            raise ModuleExecutionError(
                "영역 분류 이후 Excel 파일이 변경되었습니다. 앞 모듈부터 다시 실행하세요"
            )

        workbook = None
        try:
            workbook = openpyxl.load_workbook(
                workbook_path,
                read_only=False,
                data_only=True,
                keep_vba=workbook_path.suffix.lower() == ".xlsm",
            )
            items: List[Dict[str, Any]] = []
            seen_cell_ids: set[str] = set()
            readers: Dict[str, WorksheetValueReader] = {}
            total_tables = len(input_data.tables)
            self.report_progress(
                {
                    "phase": "serialization_tables",
                    "completed_tables": 0,
                    "total_tables": total_tables,
                    "completed_items": 0,
                }
            )
            for table_index, table in enumerate(input_data.tables, start=1):
                if table.sheet_name not in workbook.sheetnames:
                    raise ModuleExecutionError(
                        f"Excel 시트를 찾을 수 없습니다: {table.sheet_name}"
                    )
                reader = readers.get(table.sheet_name)
                if reader is None:
                    worksheet = workbook[table.sheet_name]
                    if not worksheet_visible(worksheet):
                        raise ModuleExecutionError(
                            f"숨겨진 Excel 시트는 직렬화할 수 없습니다: {table.sheet_name}"
                        )
                    reader = WorksheetValueReader(worksheet)
                    readers[table.sheet_name] = reader
                items.extend(
                    self._table_documents(
                        reader,
                        table,
                        seen_cell_ids,
                        variant_mode=getattr(input_data, "variant_mode", "both"),
                    )
                )
                self.report_progress(
                    {
                        "phase": "serialization_tables",
                        "completed_tables": table_index,
                        "total_tables": total_tables,
                        "completed_items": len(items),
                        "current_sheet": table.sheet_name,
                    }
                )
        finally:
            if workbook is not None:
                workbook.close()

        return {
            "file_name": workbook_path.name,
            "workbook_hash": current_hash,
            "items": items,
        }


# ==============================================================================
# 2. Exhaustive Cell Header Serializer
# ==============================================================================

EXHAUSTIVE_SERIALIZATION_VERSION = "exhaustive-cell-v1-visible-only"


class ExhaustiveCellTextSerializerInputDTO(WorkbookSelectionDTO):
    """Workbook identity and visible sheet selection."""


class ExhaustiveCellTextSerializerConfigDTO(ModuleConfigDTO):
    variant_mode: Literal["header_only", "header_with_value", "both"] = Field(
        default="header_only",
        description=(
            "각 헤더 조합에서 생성할 검색 문서 형태. header_only는 Cell Value를 ?로 "
            "두고, header_with_value는 실제 셀 값을 포함합니다"
        ),
    )
    deduplicate_header_values: bool = Field(
        default=True,
        description=(
            "같은 방향에서 값이 동일한 여러 셀은 같은 직렬화 문장을 만들므로 한 후보로 "
            "합칩니다. 끄면 셀 좌표별 조합을 모두 생성합니다"
        ),
    )
    max_documents: int = Field(
        default=250_000,
        ge=1,
        le=10_000_000,
        description=(
            "조합 폭증으로 프로세스가 종료되는 것을 막는 안전 한도. 초과 시 일부만 "
            "저장하지 않고 실행 전체를 실패시킵니다"
        ),
    )


class ExhaustiveCellTextSerializerExecutionDTO(
    ExhaustiveCellTextSerializerInputDTO,
    ExhaustiveCellTextSerializerConfigDTO,
):
    """Internal union of workbook data and serialization policy."""


@dataclass(frozen=True)
class PopulatedCell:
    row: int
    column: int
    coord: str
    value: str


@dataclass(frozen=True)
class SheetCells:
    sheet_name: str
    cells: List[PopulatedCell]
    rows: Dict[int, List[PopulatedCell]]
    columns: Dict[int, List[PopulatedCell]]


class ExhaustiveCellTextSerializerModule(BaseModule):
    """Serialize every distinct left × above header combination without a model."""

    definition = ModuleDefinition(
        type="exhaustive_cell_text_serializer",
        label="Exhaustive Cell Header Serializer",
        category="Transform",
        description=(
            "모든 표시 값 셀을 데이터 셀로 보고 왼쪽 행 후보와 위쪽 열 후보의 "
            "전체 조합을 결정적으로 직렬화합니다."
        ),
        inputs=["input"],
        outputs=["output"],
        config_fields=[
            "variant_mode",
            "deduplicate_header_values",
            "max_documents",
        ],
        raw_output=True,
        version=EXHAUSTIVE_SERIALIZATION_VERSION,
    )
    input_model = ExhaustiveCellTextSerializerInputDTO
    config_model = ExhaustiveCellTextSerializerConfigDTO
    execution_model = ExhaustiveCellTextSerializerExecutionDTO
    output_model = CellTextSerializerOutput

    def __init__(
        self,
        catalog: WorkbookCatalog | None = None,
        processed_dir: Path = PROCESSED_DATA_DIR,
    ) -> None:
        self.catalog = catalog or WorkbookCatalog(processed_dir)

    @staticmethod
    def _ordered_unique(cells: Iterable[PopulatedCell]) -> List[PopulatedCell]:
        seen: set[str] = set()
        unique: List[PopulatedCell] = []
        for cell in cells:
            if cell.value in seen:
                continue
            seen.add(cell.value)
            unique.append(cell)
        return unique

    @classmethod
    def _candidates(
        cls,
        cells: Iterable[PopulatedCell],
        deduplicate: bool,
    ) -> Sequence[Optional[PopulatedCell]]:
        candidates = list(cells)
        if deduplicate:
            candidates = cls._ordered_unique(candidates)
        return candidates or [None]

    @staticmethod
    def _read_sheet(worksheet) -> SheetCells:
        visibility = WorksheetVisibility.from_worksheet(worksheet)
        cells: List[PopulatedCell] = []
        rows: Dict[int, List[PopulatedCell]] = {}
        columns: Dict[int, List[PopulatedCell]] = {}

        for worksheet_row in worksheet.iter_rows():
            for cell in worksheet_row:
                if isinstance(cell, MergedCell):
                    continue
                if not visibility.cell_visible(cell.row, cell.column):
                    continue
                value = format_cell_value(cell.value)
                if value is None:
                    continue
                populated = PopulatedCell(
                    row=cell.row,
                    column=cell.column,
                    coord=cell.coordinate,
                    value=value,
                )
                cells.append(populated)
                rows.setdefault(cell.row, []).append(populated)
                columns.setdefault(cell.column, []).append(populated)

        return SheetCells(
            sheet_name=worksheet.title,
            cells=cells,
            rows=rows,
            columns=columns,
        )

    @classmethod
    def _header_candidates(
        cls,
        sheet: SheetCells,
        target: PopulatedCell,
        deduplicate: bool,
    ) -> tuple[
        Sequence[Optional[PopulatedCell]],
        Sequence[Optional[PopulatedCell]],
    ]:
        left = cls._candidates(
            (
                cell
                for cell in sheet.rows.get(target.row, ())
                if cell.column < target.column
            ),
            deduplicate,
        )
        above = cls._candidates(
            (
                cell
                for cell in sheet.columns.get(target.column, ())
                if cell.row < target.row
            ),
            deduplicate,
        )
        return left, above

    @staticmethod
    def _variant_values(
        mode: Literal["header_only", "header_with_value", "both"],
        cell_value: str,
    ) -> Sequence[tuple[Literal["header_only", "header_with_value"], str]]:
        if mode == "header_only":
            return [("header_only", UNKNOWN_FIELD)]
        if mode == "header_with_value":
            return [("header_with_value", cell_value)]
        return [
            ("header_only", UNKNOWN_FIELD),
            ("header_with_value", cell_value),
        ]

    @classmethod
    def _document_count(
        cls,
        sheets: Sequence[SheetCells],
        input_data: ExhaustiveCellTextSerializerExecutionDTO,
    ) -> int:
        variants = 2 if input_data.variant_mode == "both" else 1
        return sum(
            len(left) * len(above) * variants
            for sheet in sheets
            for target in sheet.cells
            for left, above in [
                cls._header_candidates(
                    sheet,
                    target,
                    input_data.deduplicate_header_values,
                )
            ]
        )

    @classmethod
    def _documents(
        cls,
        sheets: Sequence[SheetCells],
        input_data: ExhaustiveCellTextSerializerExecutionDTO,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[Dict[str, Any]]:
        documents: List[Dict[str, Any]] = []
        for sheet_index, sheet in enumerate(sheets, start=1):
            canonical_name = canonical_sheet_name(sheet.sheet_name)
            code = sheet_code(sheet.sheet_name)
            for target in sheet.cells:
                left_candidates, above_candidates = cls._header_candidates(
                    sheet,
                    target,
                    input_data.deduplicate_header_values,
                )
                for left in left_candidates:
                    row_headers = [left.value] if left is not None else []
                    for above in above_candidates:
                        column_headers = [above.value] if above is not None else []
                        for variant, serialized_value in cls._variant_values(
                            input_data.variant_mode,
                            target.value,
                        ):
                            documents.append(
                                {
                                    "cell_id": f"{code} Cell {target.coord}",
                                    "sheet_name": canonical_name,
                                    "cell_coord": target.coord,
                                    "row_header": row_headers,
                                    "column_header": column_headers,
                                    "cell_value": target.value,
                                    "variant": variant,
                                    "text": serialize_structured_cell(
                                        canonical_name,
                                        row_headers,
                                        column_headers,
                                        serialized_value,
                                    ),
                                }
                            )
            if progress_callback is not None:
                progress_callback(sheet_index, len(documents))
        return documents

    def execute(
        self,
        input_data: ExhaustiveCellTextSerializerInputDTO,
        config: Optional[ExhaustiveCellTextSerializerConfigDTO] = None,
    ) -> Dict[str, Any]:
        if isinstance(input_data, ExhaustiveCellTextSerializerExecutionDTO):
            settings = input_data
        else:
            cfg = config or ExhaustiveCellTextSerializerConfigDTO()
            settings = ExhaustiveCellTextSerializerExecutionDTO(
                **input_data.model_dump(),
                **cfg.model_dump(),
            )
        try:
            workbook_path = self.catalog.resolve(settings.file_name)
            current_hash = self.catalog.sha256(workbook_path)
        except (OSError, ValueError, WorkbookCatalogError) as error:
            raise ModuleExecutionError(str(error)) from error
        if current_hash != settings.workbook_hash:
            raise ModuleExecutionError(
                "파일 선택 이후 Excel 파일이 변경되었습니다. 앞 모듈부터 다시 실행하세요"
            )

        workbook = None
        try:
            workbook = openpyxl.load_workbook(
                workbook_path,
                read_only=False,
                data_only=True,
                keep_vba=workbook_path.suffix.lower() == ".xlsm",
            )
            sheets: List[SheetCells] = []
            total_sheets = len(settings.sheet_names)
            self.report_progress(
                {
                    "phase": "workbook_scan",
                    "completed_sheets": 0,
                    "total_sheets": total_sheets,
                }
            )
            for sheet_index, sheet_name in enumerate(settings.sheet_names, start=1):
                if sheet_name not in workbook.sheetnames:
                    raise ModuleExecutionError(
                        f"Excel 시트를 찾을 수 없습니다: {sheet_name}"
                    )
                worksheet = workbook[sheet_name]
                if not worksheet_visible(worksheet):
                    raise ModuleExecutionError(
                        f"숨겨진 Excel 시트는 직렬화할 수 없습니다: {sheet_name}"
                    )
                sheets.append(self._read_sheet(worksheet))
                self.report_progress(
                    {
                        "phase": "workbook_scan",
                        "completed_sheets": sheet_index,
                        "total_sheets": total_sheets,
                        "current_sheet": sheet_name,
                    }
                )

            document_count = self._document_count(sheets, settings)
            if document_count == 0:
                raise ModuleExecutionError("직렬화할 표시 값 셀이 없습니다")
            if document_count > settings.max_documents:
                raise ModuleExecutionError(
                    "전체 헤더 조합 문서가 안전 한도를 초과합니다: "
                    f"{document_count:,}개 > {settings.max_documents:,}개. "
                    "중복 헤더 값 병합을 켜거나 max_documents를 명시적으로 늘리세요"
                )
            self.report_progress(
                {
                    "phase": "document_generation",
                    "completed_sheets": 0,
                    "total_sheets": len(sheets),
                    "completed_items": 0,
                    "total_items": document_count,
                }
            )
            items = self._documents(
                sheets,
                settings,
                progress_callback=lambda completed_sheets, completed_items: self.report_progress(
                    {
                        "phase": "document_generation",
                        "completed_sheets": completed_sheets,
                        "total_sheets": len(sheets),
                        "completed_items": completed_items,
                        "total_items": document_count,
                    }
                ),
            )
        finally:
            if workbook is not None:
                workbook.close()

        return {
            "file_name": workbook_path.name,
            "workbook_hash": current_hash,
            "items": items,
        }


__all__ = [
    "CellTextDocumentDTO",
    "CellTextSerializerConfigDTO",
    "CellTextSerializerExecutionDTO",
    "CellTextSerializerInputDTO",
    "CellTextSerializerModule",
    "CellTextSerializerOutput",
    "EXHAUSTIVE_SERIALIZATION_VERSION",
    "ExhaustiveCellTextSerializerConfigDTO",
    "ExhaustiveCellTextSerializerExecutionDTO",
    "ExhaustiveCellTextSerializerInputDTO",
    "ExhaustiveCellTextSerializerModule",
    "PopulatedCell",
    "SheetCells",
]