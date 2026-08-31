"""시각적 렌더링(VLM) 및 셀 그리드 기하학을 결합하여 복합 엑셀 시트 내 다중 표 구조와 헤더 계층을 감지하는 모듈.

엑셀 워크시트 이미지를 렌더링하고 VLM(Vision-Language Model)에 전달하여
시트 내 개별 표 영역(테이블 바운딩 박스), 열/행 헤더 영역, 데이터 본문 영역, 복합 병합 헤더 트리를 감지합니다.

Example:
    Input DTO (입력 예시):
    ```json
    {
      "file_name": "samsung_2023.xlsx",
      "workbook_hash": "a1b2c3d4...",
      "sheet_names": ["손익계산서"]
    }
    ```

    Output DTO (출력 예시):
    ```json
    {
      "file_name": "samsung_2023.xlsx",
      "workbook_hash": "a1b2c3d4...",
      "tables": [
        {
          "table_id": "tbl_01",
          "sheet_name": "손익계산서",
          "table_type": "primary",
          "bounding_box": {"start_row": 3, "start_col": 1, "end_row": 45, "end_col": 6},
          "column_header_range": {"start_row": 3, "start_col": 1, "end_row": 4, "end_col": 6},
          "row_header_range": {"start_row": 5, "start_col": 1, "end_row": 45, "end_col": 1},
          "data_range": {"start_row": 5, "start_col": 2, "end_row": 45, "end_col": 6}
        }
      ]
    }
    ```
"""

from __future__ import annotations

import concurrent.futures
import itertools
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Protocol, Tuple

import openpyxl
from openpyxl.utils.cell import range_boundaries
from pydantic import Field

from backend.core.settings import SPREADSHEET_ARTIFACT_DIR
from backend.platform.openai.responses import OpenAIResponseResult, OpenAIResponsesError
from backend.storage.spreadsheets.cell_semantics import (
    collect_non_empty_cells,
    compact_sheet_context,
)
from backend.storage.spreadsheets.cell_type_overlay import render_cell_type_overlay
from backend.storage.spreadsheets.cell_visibility import WorksheetVisibility, worksheet_visible
from backend.storage.spreadsheets.grid_structure import build_column_header_tree
from backend.storage.spreadsheets.prompt_guidance import (
    TABLE_UNIFICATION_GUIDANCE,
    TEXT_CELL_ROLE_GUIDANCE,
)
from backend.storage.spreadsheets.sheet_renderer import ExcelSheetRenderer
from backend.storage.spreadsheets.table_geometry import CellBounds, SheetLayout, cell_bounds_bbox
from backend.storage.spreadsheets.workbook_catalog import WorkbookCatalog
from modules.common.base_module import (
    BaseModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleDTO,
    ModuleExecutionError,
    ModuleTaskPolicy,
)
from modules.common.config import (
    DEFAULT_STRUCTURE_MAX_COLUMNS,
    DEFAULT_STRUCTURE_MAX_CONTEXT_CELLS,
    DEFAULT_STRUCTURE_MAX_OUTPUT_TOKENS,
    DEFAULT_STRUCTURE_MAX_ROWS,
    DEFAULT_VLM_MODEL,
    DEFAULT_VLM_REASONING_EFFORT,
    DEFAULT_VLM_TIMEOUT_SECONDS,
)
from modules.storage.processed_file_selector import WorkbookSelectionDTO

logger = logging.getLogger(__name__)


def _safe_name(value: str) -> str:
    return "".join("_" if character in '\\/*?:"<>| ' else character for character in value).strip(
        "_"
    )


# ==============================================================================
# 2. Structure DTOs & Item Models
# ==============================================================================
class ColumnHeaderNodeDTO(ModuleDTO):
    """One coordinate-backed node in a worksheet column-header hierarchy."""

    name: str
    col_start: int
    col_end: int
    row_start: int
    row_end: int
    children: List["ColumnHeaderNodeDTO"] = Field(default_factory=list)


class ClassifiedRegionDTO(ModuleDTO):
    region_id: str
    type: Literal["title", "column_header", "row_header", "data"]
    excel_range: str
    bbox_px: Tuple[float, float, float, float]
    rows: Tuple[int, int]
    columns: Tuple[int, int]
    parent_ids: List[str]


class ClassifiedTableDTO(ModuleDTO):
    sheet_name: str
    table_index: int
    excel_range: str
    regions: List[ClassifiedRegionDTO]
    header_tree: List[ColumnHeaderNodeDTO] = Field(default_factory=list)


class SpreadsheetStructureOutput(ModuleDTO):
    """Shared output contract accepted directly by the cell serializer."""

    file_name: str
    workbook_hash: str
    company_name: Optional[str] = Field(
        default=None,
        description="알려진 경우 직렬화 문서에 포함할 공식 기업명",
    )
    sheet_names: List[str] = Field(
        default_factory=list,
        description="구조 분석 대상으로 선택된 표시 시트명",
    )
    tables: List[ClassifiedTableDTO]
    failed_sheets: List[Dict[str, str]] = Field(
        default_factory=list,
        description="분석하지 못한 시트명과 실패 사유",
    )


LUNA_VLM_SYSTEM_PROMPT = f"""You identify every table and its internal regions in an Excel worksheet.
Hidden sheets, hidden rows, and hidden columns are intentionally absent and must never be inferred.

You receive exactly one high-detail image containing the complete visible worksheet. It is never a crop, tile, or preselected candidate region. Inspect the entire image globally before deciding table boundaries, including sparse areas and tables separated by blank rows or columns.

The image preserves the original worksheet style while populated cells are tinted and labeled by exact Excel coordinate. Colors are: text amber, number green, date blue, boolean purple, error red, unresolved formula gray. A magenta inner border marks a formula. Exact coordinate, type, value, formula, and merged-range facts for the complete sheet are supplied as text and are authoritative.

{TEXT_CELL_ROLE_GUIDANCE}

{TABLE_UNIFICATION_GUIDANCE}

Return every independent rectangular table in the worksheet. A table must contain data cells; do not emit decorations, isolated notes, or empty rectangles. Every returned coordinate must be inside sheet_range. Use:
- excel_range: the complete visible table.
- title_range: title rows above this table's data, or null.
- column_header_range: every visible column-header level above the data, or null.
- row_header_range: label columns left of the data, or null.
- data_range: the complete value matrix.

All ranges use inclusive Excel coordinates and semantic regions must not overlap. For example, when row_header_range ends at D, data_range must start at E or later. Never repeat a row-header column inside data_range.

Use the full-sheet context to keep one logical table whole instead of splitting it at image boundaries. Do not propose search candidates and do not omit a table because its location is uncertain. Return only JSON matching the supplied schema."""


LUNA_VLM_USER_TEMPLATE = """Analyze the complete visible worksheet {sheet_name}.
Complete visible sheet range: {sheet_range}
The compact tuple format is [excel_coord, value_type, value, optional_flags].
Exact full-sheet context:
{sheet_context}"""


LUNA_SHEET_RESPONSE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "tables": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "excel_range": {"type": "string"},
                    "title_range": {"type": ["string", "null"]},
                    "column_header_range": {"type": ["string", "null"]},
                    "row_header_range": {"type": ["string", "null"]},
                    "data_range": {"type": "string"},
                },
                "required": [
                    "excel_range",
                    "title_range",
                    "column_header_range",
                    "row_header_range",
                    "data_range",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["tables"],
    "additionalProperties": False,
}


class LunaVisionClient(Protocol):
    def complete_vision_structured(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        image_path: Path,
        schema_name: str,
        json_schema: Dict[str, Any],
        reasoning_effort: Literal["none", "low", "medium", "high"],
        max_output_tokens: int,
        timeout_seconds: int,
    ) -> OpenAIResponseResult | str: ...


class LunaVlmStructureDetectorInputDTO(WorkbookSelectionDTO):
    """Workbook identity and visible sheet selection."""


class LunaVlmStructureDetectorConfigDTO(ModuleConfigDTO):
    model: str = Field(
        default=DEFAULT_VLM_MODEL,
        min_length=1,
        description="OpenAI Responses API 멀티모달 모델 ID",
    )
    max_rows: int = Field(
        default=DEFAULT_STRUCTURE_MAX_ROWS,
        ge=1,
        le=2000,
        description="시트에서 분석할 최대 행 수",
    )
    max_columns: int = Field(
        default=DEFAULT_STRUCTURE_MAX_COLUMNS,
        ge=1,
        le=200,
        description="시트에서 분석할 최대 열 수",
    )
    max_context_cells: int = Field(
        default=DEFAULT_STRUCTURE_MAX_CONTEXT_CELLS,
        ge=100,
        le=100000,
        description="한 시트에서 좌표 컨텍스트로 전달할 최대 값 셀 수",
    )
    reasoning_effort: Literal["none", "low", "medium", "high"] = Field(
        default=DEFAULT_VLM_REASONING_EFFORT,
        description="Luna 추론 강도",
    )
    max_output_tokens: int = Field(
        default=DEFAULT_STRUCTURE_MAX_OUTPUT_TOKENS,
        ge=1000,
        le=32000,
        description="시트별 최대 출력 토큰",
    )
    timeout_seconds: int = Field(
        default=DEFAULT_VLM_TIMEOUT_SECONDS,
        ge=30,
        le=900,
        description="시트별 API 요청 제한 시간(초)",
    )
    validation_retries: int = Field(
        default=1, ge=0, le=2, description="좌표 규칙 위반 응답의 교정 재시도 횟수"
    )
    max_concurrency: int = Field(
        default=4,
        ge=1,
        le=16,
        description="동시에 실행할 시트별 VLM 요청 수",
    )
    system_prompt: str = Field(
        default=LUNA_VLM_SYSTEM_PROMPT,
        min_length=1,
        description="전체 시트 구조 식별 시스템 프롬프트",
    )
    user_prompt_template: str = Field(
        default=LUNA_VLM_USER_TEMPLATE,
        min_length=1,
        description="sheet_name, sheet_range, sheet_context 변수를 지원하는 전체 시트 프롬프트",
    )


class LunaVlmStructureDetectorExecutionDTO(
    LunaVlmStructureDetectorInputDTO,
    LunaVlmStructureDetectorConfigDTO,
):
    """Validated execution payload for whole-sheet Responses inference."""


class VlmTableDecisionDTO(ModuleDTO):
    excel_range: str = Field(description="전체 테이블 Excel 범위")
    title_range: Optional[str] = Field(default=None, description="테이블 제목 범위")
    column_header_range: Optional[str] = Field(default=None, description="열 헤더 범위")
    row_header_range: Optional[str] = Field(default=None, description="행 헤더 범위")
    data_range: str = Field(description="데이터 값 행렬 범위")


LocalVlmTableDecisionDTO = VlmTableDecisionDTO


class LunaSheetDecisionDTO(ModuleDTO):
    tables: List[VlmTableDecisionDTO]


class LunaVlmStructureDetectorOutput(SpreadsheetStructureOutput):
    pass


def _bounds(value: str, field_name: str) -> CellBounds:
    try:
        min_column, min_row, max_column, max_row = range_boundaries(value)
    except (TypeError, ValueError) as error:
        raise ModuleExecutionError(f"VLM {field_name} 범위가 올바르지 않습니다: {value}") from error
    if min_column is None or min_row is None or max_column is None or max_row is None:
        raise ModuleExecutionError(f"VLM {field_name}은 셀 사각형 범위여야 합니다: {value}")
    return CellBounds(min_row, max_row, min_column, max_column)


def _contains(outer: CellBounds, inner: CellBounds) -> bool:
    return (
        outer.min_row <= inner.min_row <= inner.max_row <= outer.max_row
        and outer.min_column <= inner.min_column <= inner.max_column <= outer.max_column
    )


def _visible_bounds(
    bounds: CellBounds,
    visibility: WorksheetVisibility,
    field_name: str,
) -> CellBounds:
    rows = [
        row for row in range(bounds.min_row, bounds.max_row + 1) if not visibility.row_hidden(row)
    ]
    columns = [
        column
        for column in range(bounds.min_column, bounds.max_column + 1)
        if not visibility.column_hidden(column)
    ]
    if not rows or not columns:
        raise ModuleExecutionError(f"VLM {field_name}에 표시된 셀이 없습니다: {bounds.excel_range}")
    return CellBounds(rows[0], rows[-1], columns[0], columns[-1])


def unify_sheet_tables(
    tables: List[VlmTableDecisionDTO],
) -> List[VlmTableDecisionDTO]:
    """Merge vertically stacked sub-sections sharing the same column timeline into unified tables."""
    if len(tables) <= 1:
        return tables

    parsed_tables = []
    for table in tables:
        try:
            data_bounds = _bounds(table.data_range, "data_range")
            excel_bounds = _bounds(table.excel_range, "excel_range")
            header_bounds = (
                _bounds(table.column_header_range, "column_header_range")
                if table.column_header_range
                else None
            )
            title_bounds = _bounds(table.title_range, "title_range") if table.title_range else None
            row_bounds = (
                _bounds(table.row_header_range, "row_header_range")
                if table.row_header_range
                else None
            )
            parsed_tables.append(
                (table, excel_bounds, data_bounds, header_bounds, title_bounds, row_bounds)
            )
        except ModuleExecutionError:
            return tables

    first_data = parsed_tables[0][2]
    all_same_columns = all(
        item[2].min_column == first_data.min_column and item[2].max_column == first_data.max_column
        for item in parsed_tables
    )

    ordered_tables = sorted(parsed_tables, key=lambda item: item[1].min_row)
    vertically_contiguous = all(
        current[1].max_row < following[1].min_row and following[1].min_row - current[1].max_row <= 2
        for current, following in itertools.pairwise(ordered_tables)
    )
    continuation_sections = all(item[3] is None and item[4] is None for item in ordered_tables[1:])

    if all_same_columns and vertically_contiguous and continuation_sections:
        primary_header = next(
            (item[3] for item in parsed_tables if item[3] is not None),
            None,
        )
        primary_title = next(
            (item[4] for item in parsed_tables if item[4] is not None),
            None,
        )
        min_whole_row = min(item[1].min_row for item in parsed_tables)
        max_whole_row = max(item[1].max_row for item in parsed_tables)
        min_whole_col = min(item[1].min_column for item in parsed_tables)
        max_whole_col = max(item[1].max_column for item in parsed_tables)

        min_data_row = min(item[2].min_row for item in parsed_tables)
        max_data_row = max(item[2].max_row for item in parsed_tables)

        row_header_cols = [item[5] for item in parsed_tables if item[5] is not None]
        if row_header_cols:
            min_r_col = min(r.min_column for r in row_header_cols)
            max_r_col = max(r.max_column for r in row_header_cols)
            unified_row_header = CellBounds(
                min_data_row, max_data_row, min_r_col, max_r_col
            ).excel_range
        else:
            unified_row_header = None

        return [
            VlmTableDecisionDTO(
                excel_range=CellBounds(
                    min_whole_row, max_whole_row, min_whole_col, max_whole_col
                ).excel_range,
                title_range=primary_title.excel_range if primary_title else None,
                column_header_range=primary_header.excel_range if primary_header else None,
                row_header_range=unified_row_header,
                data_range=CellBounds(
                    min_data_row, max_data_row, first_data.min_column, first_data.max_column
                ).excel_range,
            )
        ]

    return tables


def _replace_prompt_variables(template: str, values: Dict[str, str]) -> str:
    result = template
    for name, value in values.items():
        result = result.replace("{" + name + "}", value)
    return result


def _validated_sheet_decision(
    table: VlmTableDecisionDTO,
    sheet_bounds: CellBounds,
) -> VlmTableDecisionDTO:
    whole = _bounds(table.excel_range, "excel_range")
    if not _contains(sheet_bounds, whole):
        raise ModuleExecutionError(
            f"Luna 응답 범위가 시트 {sheet_bounds.excel_range}를 벗어났습니다: {table.excel_range}"
        )
    for field_name in (
        "title_range",
        "column_header_range",
        "row_header_range",
        "data_range",
    ):
        value = getattr(table, field_name)
        if value and not _contains(whole, _bounds(value, field_name)):
            raise ModuleExecutionError(f"Luna {field_name}이 excel_range를 벗어났습니다: {value}")
    return table


TableRangeMap = Dict[str, Optional[CellBounds]]


def _parsed_table_ranges(table: VlmTableDecisionDTO) -> TableRangeMap:
    return {
        "excel_range": _bounds(table.excel_range, "excel_range"),
        "title_range": _bounds(table.title_range, "title_range") if table.title_range else None,
        "column_header_range": (
            _bounds(table.column_header_range, "column_header_range")
            if table.column_header_range
            else None
        ),
        "row_header_range": (
            _bounds(table.row_header_range, "row_header_range") if table.row_header_range else None
        ),
        "data_range": _bounds(table.data_range, "data_range"),
    }


def _required_range(ranges: TableRangeMap, name: str) -> CellBounds:
    bounds = ranges[name]
    if bounds is None:
        raise ModuleExecutionError(f"VLM {name}가 누락되었습니다")
    return bounds


def _visible_table_ranges(
    table: VlmTableDecisionDTO,
    layout: SheetLayout,
    visibility: WorksheetVisibility,
) -> TableRangeMap:
    ranges = _parsed_table_ranges(table)
    whole = _required_range(ranges, "excel_range")
    _required_range(ranges, "data_range")
    sheet = CellBounds(1, layout.max_row, 1, layout.max_column)
    if not _contains(sheet, whole):
        raise ModuleExecutionError(
            f"VLM 테이블 범위가 분석 시트를 벗어났습니다: {whole.excel_range}"
        )
    for field_name, bounds in ranges.items():
        if field_name != "excel_range" and bounds is not None and not _contains(whole, bounds):
            raise ModuleExecutionError(
                f"VLM {field_name}이 테이블 범위를 벗어났습니다: {bounds.excel_range}"
            )
    return {
        field_name: (
            _visible_bounds(bounds, visibility, field_name) if bounds is not None else None
        )
        for field_name, bounds in ranges.items()
    }


def _separate_title_and_column_header(ranges: TableRangeMap) -> None:
    title = ranges["title_range"]
    column_header = ranges["column_header_range"]
    if not title or not column_header or title.max_row < column_header.min_row:
        return
    ranges["title_range"] = (
        CellBounds(
            title.min_row,
            column_header.min_row - 1,
            title.min_column,
            title.max_column,
        )
        if title.min_row < column_header.min_row
        else None
    )


def _trim_vertical_range_before_data(
    bounds: Optional[CellBounds],
    data: CellBounds,
) -> Optional[CellBounds]:
    if not bounds or bounds.max_row < data.min_row:
        return bounds
    if bounds.min_row >= data.min_row:
        return None
    return CellBounds(
        bounds.min_row,
        data.min_row - 1,
        bounds.min_column,
        bounds.max_column,
    )


def _separate_headers_and_data(ranges: TableRangeMap) -> None:
    title = ranges["title_range"]
    column_header = ranges["column_header_range"]
    data = _required_range(ranges, "data_range")
    header_bottom = column_header.max_row if column_header else title.max_row if title else None
    if header_bottom is not None and header_bottom >= data.min_row:
        if data.max_row > header_bottom:
            ranges["data_range"] = CellBounds(
                header_bottom + 1,
                data.max_row,
                data.min_column,
                data.max_column,
            )
        else:
            ranges["column_header_range"] = _trim_vertical_range_before_data(
                column_header,
                data,
            )
            ranges["title_range"] = _trim_vertical_range_before_data(title, data)

    data = _required_range(ranges, "data_range")
    ranges["title_range"] = _trim_vertical_range_before_data(
        ranges["title_range"],
        data,
    )
    ranges["column_header_range"] = _trim_vertical_range_before_data(
        ranges["column_header_range"],
        data,
    )


def _separate_row_header_and_data(ranges: TableRangeMap) -> None:
    row_header = ranges["row_header_range"]
    data = _required_range(ranges, "data_range")
    if row_header and row_header.max_column >= data.min_column:
        if row_header.min_column < data.min_column:
            row_header = CellBounds(
                row_header.min_row,
                row_header.max_row,
                row_header.min_column,
                data.min_column - 1,
            )
        elif row_header.max_column < data.max_column:
            data = CellBounds(
                data.min_row,
                data.max_row,
                row_header.max_column + 1,
                data.max_column,
            )
            ranges["data_range"] = data
        else:
            row_header = None
        ranges["row_header_range"] = row_header

    if row_header:
        ranges["row_header_range"] = CellBounds(
            data.min_row,
            data.max_row,
            row_header.min_column,
            row_header.max_column,
        )
    column_header = ranges["column_header_range"]
    if column_header:
        ranges["column_header_range"] = CellBounds(
            column_header.min_row,
            data.min_row - 1,
            data.min_column,
            data.max_column,
        )


@dataclass(frozen=True)
class PreparedSheet:
    sheet_name: str
    sheet_bounds: CellBounds
    typed_path: Path
    layout: SheetLayout
    visibility: WorksheetVisibility
    cells: List[Dict[str, Any]]
    value_sheet: Any


@dataclass
class SheetAnalysisBatch:
    tables_by_sheet: Dict[str, List[Dict[str, Any]]]
    failed_sheets: List[Dict[str, str]]
    analyzed_sheet_count: int
    usage: Dict[str, int]
    latency_seconds: float


class LunaVlmStructureDetectorModule(BaseModule):
    definition = ModuleDefinition(
        type="luna_vlm_structure_detector",
        label="Luna Full-Sheet Structure Detector",
        category="Logic",
        description="후보 영역이나 타일 분할 없이 표시된 시트 전체 이미지와 좌표 컨텍스트를 한 번에 분석합니다.",
        inputs=["input"],
        outputs=["output"],
        config_fields=[
            "model",
            "max_rows",
            "max_columns",
            "max_context_cells",
            "reasoning_effort",
            "max_output_tokens",
            "timeout_seconds",
            "validation_retries",
            "max_concurrency",
            "system_prompt",
            "user_prompt_template",
        ],
        raw_output=True,
        version="5",
        task=ModuleTaskPolicy(
            retries=2,
            retry_delay_seconds=5,
            timeout_seconds=1800,
            tags=["external-api", "vlm"],
            resource_profile="high-memory",
        ),
    )
    input_model = LunaVlmStructureDetectorInputDTO
    config_model = LunaVlmStructureDetectorConfigDTO
    output_model = LunaVlmStructureDetectorOutput

    def __init__(
        self,
        vision_client: LunaVisionClient,
        catalog: WorkbookCatalog,
        renderer: ExcelSheetRenderer,
        artifact_dir: Path = SPREADSHEET_ARTIFACT_DIR,
    ) -> None:
        if vision_client is None:
            raise ValueError("LunaVlmStructureDetectorModule에는 vision_client 주입이 필요합니다")
        self.vision_client = vision_client
        self.catalog = catalog
        self.renderer = renderer
        self.artifact_dir = artifact_dir
        self.structure_assembler = self
        self.last_usage: Optional[Dict[str, int]] = None
        self.last_model: Optional[str] = None
        self.last_duration_seconds: float = 0.0

    @staticmethod
    def _region(
        region_id: str,
        region_type: str,
        bounds: CellBounds,
        layout,
        parent_ids: List[str],
    ) -> Dict[str, Any]:
        return {
            "region_id": region_id,
            "type": region_type,
            "excel_range": bounds.excel_range,
            "bbox_px": cell_bounds_bbox(bounds, layout),
            "rows": (bounds.min_row, bounds.max_row),
            "columns": (bounds.min_column, bounds.max_column),
            "parent_ids": parent_ids,
        }

    @staticmethod
    def _validate_table(
        table: VlmTableDecisionDTO,
        layout: SheetLayout,
        visibility: WorksheetVisibility,
    ) -> Dict[str, CellBounds | None]:
        ranges = _visible_table_ranges(table, layout, visibility)
        _separate_title_and_column_header(ranges)
        _separate_headers_and_data(ranges)
        _separate_row_header_and_data(ranges)
        return ranges

    def _table_output(
        self,
        table_index: int,
        table: VlmTableDecisionDTO,
        worksheet,
        layout,
    ) -> Dict[str, Any]:
        visibility = WorksheetVisibility.from_worksheet(worksheet)
        named = self._validate_table(table, layout, visibility)
        whole = named["excel_range"]
        data = named["data_range"]
        if whole is None or data is None:
            raise ModuleExecutionError("VLM excel_range 또는 data_range가 누락되었습니다")
        prefix = f"table_{table_index}"
        regions: List[Dict[str, Any]] = []
        parents: List[str] = []

        for key, region_type in (
            ("title_range", "title"),
            ("column_header_range", "column_header"),
        ):
            bounds = named.get(key)
            if bounds is None:
                continue
            region_id = f"{prefix}_{region_type}"
            regions.append(self._region(region_id, region_type, bounds, layout, list(parents)))
            parents.append(region_id)

        row_header = named.get("row_header_range")
        if row_header is not None:
            row_header_id = f"{prefix}_row_header"
            regions.append(
                self._region(row_header_id, "row_header", row_header, layout, list(parents))
            )
            parents.append(row_header_id)
        regions.append(self._region(f"{prefix}_data", "data", data, layout, list(parents)))

        column_header = named.get("column_header_range")
        return {
            "sheet_name": worksheet.title,
            "table_index": table_index,
            "excel_range": whole.excel_range,
            "regions": regions,
            "header_tree": build_column_header_tree(
                worksheet,
                whole,
                column_header.min_row if column_header else data.min_row,
                column_header.max_row if column_header else data.min_row - 1,
                data.min_column,
            ),
        }

    def _analyze_sheet(
        self,
        settings: LunaVlmStructureDetectorConfigDTO,
        sheet_name: str,
        sheet_bounds: CellBounds,
        image_path: Path,
        layout: SheetLayout,
        visibility: WorksheetVisibility,
        cells: List[Dict[str, Any]],
    ) -> Tuple[List[LocalVlmTableDecisionDTO], Dict[str, int], float]:
        context = compact_sheet_context(sheet_name, layout, cells)
        prompt = _replace_prompt_variables(
            settings.user_prompt_template,
            {
                "sheet_name": sheet_name,
                "sheet_range": sheet_bounds.excel_range,
                "sheet_context": json.dumps(
                    context,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            },
        )
        previous_response = ""
        validation_error = ""
        aggregate_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cached_tokens": 0,
            "total_tokens": 0,
        }
        aggregate_latency = 0.0
        for attempt in range(settings.validation_retries + 1):
            correction = ""
            if attempt:
                correction = (
                    "\n\nThe previous JSON violated the whole-sheet coordinate rules: "
                    f"{validation_error}\nPrevious JSON: {previous_response}\n"
                    "Return a corrected complete object. All ranges must stay inside "
                    f"{sheet_bounds.excel_range}."
                )
            try:
                response = self.vision_client.complete_vision_structured(
                    model=settings.model,
                    system_prompt=settings.system_prompt,
                    user_prompt=prompt + correction,
                    image_path=image_path,
                    schema_name="luna_spreadsheet_sheet",
                    json_schema=LUNA_SHEET_RESPONSE_SCHEMA,
                    reasoning_effort=settings.reasoning_effort,
                    max_output_tokens=settings.max_output_tokens,
                    timeout_seconds=settings.timeout_seconds,
                )
                if isinstance(response, OpenAIResponseResult):
                    for key in aggregate_usage:
                        aggregate_usage[key] += int(response.usage.get(key, 0) or 0)
                    aggregate_latency += response.latency_seconds
                previous_response = (
                    response.content if isinstance(response, OpenAIResponseResult) else response
                )
                decision = LunaSheetDecisionDTO.model_validate_json(previous_response)
                unified_tables = unify_sheet_tables(decision.tables)
                tables = [
                    _validated_sheet_decision(table, sheet_bounds) for table in unified_tables
                ]
                for table in tables:
                    self.structure_assembler._validate_table(table, layout, visibility)
                return tables, aggregate_usage, aggregate_latency
            except OpenAIResponsesError:
                raise
            except (ValueError, TypeError, json.JSONDecodeError, ModuleExecutionError) as error:
                validation_error = str(error)
                if attempt >= settings.validation_retries:
                    raise ModuleExecutionError(
                        f"Luna 시트 {sheet_name} 응답을 좌표 규칙에 맞게 교정하지 못했습니다: {validation_error}"
                    ) from error
        return [], aggregate_usage, aggregate_latency

    def _prepare_sheet(
        self,
        formula_sheet: Any,
        value_sheet: Any,
        sheet_name: str,
        output_root: Path,
        config: LunaVlmStructureDetectorConfigDTO,
    ) -> PreparedSheet:
        safe_sheet = _safe_name(sheet_name)
        rendered_path = output_root / "rendered" / f"{safe_sheet}.png"
        typed_path = output_root / "typed" / f"{safe_sheet}.png"
        layout = self.renderer.render(
            value_sheet,
            rendered_path,
            config.max_rows,
            config.max_columns,
        )
        cells = collect_non_empty_cells(
            formula_sheet,
            value_sheet,
            layout,
            config.max_context_cells,
        )
        render_cell_type_overlay(rendered_path, typed_path, layout, cells)
        sheet_bounds = CellBounds(
            min_row=1,
            max_row=max((cell["row"] for cell in cells), default=1),
            min_column=1,
            max_column=max((cell["column"] for cell in cells), default=1),
        )
        return PreparedSheet(
            sheet_name=sheet_name,
            sheet_bounds=sheet_bounds,
            typed_path=typed_path,
            layout=layout,
            visibility=WorksheetVisibility.from_worksheet(formula_sheet),
            cells=cells,
            value_sheet=value_sheet,
        )

    def _prepare_sheets(
        self,
        formula_workbook: Any,
        value_workbook: Any,
        sheet_names: List[str],
        output_root: Path,
        config: LunaVlmStructureDetectorConfigDTO,
    ) -> Tuple[List[PreparedSheet], List[Dict[str, str]]]:
        prepared: List[PreparedSheet] = []
        failures: List[Dict[str, str]] = []
        for sheet_name in sheet_names:
            if sheet_name not in formula_workbook.sheetnames:
                logger.warning("[Luna VLM] Excel 시트를 찾을 수 없어 건너뜁니다: %s", sheet_name)
                failures.append({"sheet_name": sheet_name, "error": "시트를 찾을 수 없습니다"})
                continue
            formula_sheet = formula_workbook[sheet_name]
            value_sheet = value_workbook[sheet_name]
            if not worksheet_visible(formula_sheet) or not worksheet_visible(value_sheet):
                logger.info("[Luna VLM] 숨겨진 시트 건너뜀: %s", sheet_name)
                failures.append({"sheet_name": sheet_name, "error": "숨겨진 시트입니다"})
                continue
            try:
                prepared.append(
                    self._prepare_sheet(
                        formula_sheet,
                        value_sheet,
                        sheet_name,
                        output_root,
                        config,
                    )
                )
            except Exception as error:
                logger.exception("[Luna VLM] 시트 '%s' 전처리 중 예외 발생", sheet_name)
                failures.append({"sheet_name": sheet_name, "error": str(error)})
        return prepared, failures

    def _call_vlm(
        self,
        config: LunaVlmStructureDetectorConfigDTO,
        context: PreparedSheet,
    ) -> Tuple[PreparedSheet, List[LocalVlmTableDecisionDTO], Dict[str, int], float]:
        print(
            f"[Luna VLM] 시트 '{context.sheet_name}' OpenAI VLM 호출 시작...",
            flush=True,
        )
        decisions, usage, latency = self._analyze_sheet(
            config,
            context.sheet_name,
            context.sheet_bounds,
            context.typed_path,
            context.layout,
            context.visibility,
            context.cells,
        )
        print(
            f"[Luna VLM] 시트 '{context.sheet_name}' OpenAI VLM 응답 완료 "
            f"({len(decisions)}개 표 감지)",
            flush=True,
        )
        return context, decisions, usage, latency

    def _assemble_sheet_tables(
        self,
        context: PreparedSheet,
        decisions: List[LocalVlmTableDecisionDTO],
    ) -> List[Dict[str, Any]]:
        tables: List[Dict[str, Any]] = []
        for table_index, decision in enumerate(decisions, start=1):
            table = self.structure_assembler._table_output(
                table_index,
                decision,
                context.value_sheet,
                context.layout,
            )
            table["sheet_name"] = context.sheet_name
            tables.append(table)
        return tables

    def _report_sheet_progress(
        self,
        analyzed_sheet_count: int,
        failed_sheet_count: int,
        total_sheet_count: int,
        *,
        active_sheets: Optional[List[str]] = None,
        include_finished: bool = False,
    ) -> None:
        progress: Dict[str, Any] = {
            "phase": "sheet_analysis",
            "completed_sheets": analyzed_sheet_count,
            "failed_sheets": failed_sheet_count,
            "total_sheets": total_sheet_count,
        }
        if active_sheets is not None:
            progress["active_sheets"] = active_sheets
        if include_finished:
            progress["finished_sheets"] = analyzed_sheet_count + failed_sheet_count
        self.report_progress(progress)

    def _analyze_prepared_sheets(
        self,
        config: LunaVlmStructureDetectorConfigDTO,
        prepared_sheets: List[PreparedSheet],
        initial_failures: List[Dict[str, str]],
        total_sheet_count: int,
    ) -> SheetAnalysisBatch:
        failures = list(initial_failures)
        self._report_sheet_progress(
            0,
            len(failures),
            total_sheet_count,
            active_sheets=[context.sheet_name for context in prepared_sheets],
        )
        tables_by_sheet: Dict[str, List[Dict[str, Any]]] = {}
        usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cached_tokens": 0,
            "total_tokens": 0,
        }
        latency_seconds = 0.0
        analyzed_sheet_count = 0
        max_workers = min(config.max_concurrency, len(prepared_sheets)) or 1
        print(
            f"[Luna VLM] {len(prepared_sheets)}개 시트 병렬 VLM 분석 시작 "
            f"(스레드 {max_workers}개)...",
            flush=True,
        )
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self._call_vlm, config, context): context
                for context in prepared_sheets
            }
            for future in concurrent.futures.as_completed(futures):
                try:
                    context, decisions, sheet_usage, sheet_latency = future.result()
                    for key in usage:
                        usage[key] += sheet_usage[key]
                    latency_seconds += sheet_latency
                    sheet_tables = self._assemble_sheet_tables(context, decisions)
                    tables_by_sheet[context.sheet_name] = sheet_tables
                    analyzed_sheet_count += 1
                    print(
                        f"[Luna VLM] 시트 '{context.sheet_name}' 테이블 "
                        f"{len(sheet_tables)}개 최종 조립 완료",
                        flush=True,
                    )
                except Exception as error:
                    failed_name = futures[future].sheet_name
                    logger.exception("[Luna VLM] 시트 '%s' 분석 중 예외 발생", failed_name)
                    failures.append({"sheet_name": failed_name, "error": str(error)})
                    print(f"[Luna VLM] 시트 분석 중 예외: {error}", flush=True)
                finally:
                    self._report_sheet_progress(
                        analyzed_sheet_count,
                        len(failures),
                        total_sheet_count,
                        include_finished=True,
                    )
        return SheetAnalysisBatch(
            tables_by_sheet=tables_by_sheet,
            failed_sheets=failures,
            analyzed_sheet_count=analyzed_sheet_count,
            usage=usage,
            latency_seconds=latency_seconds,
        )

    def _ensure_analysis_succeeded(
        self,
        batch: SheetAnalysisBatch,
        total_sheet_count: int,
    ) -> None:
        self._report_sheet_progress(
            batch.analyzed_sheet_count,
            len(batch.failed_sheets),
            total_sheet_count,
        )
        if batch.analyzed_sheet_count:
            return
        reasons = "; ".join(
            f"{failure['sheet_name']}: {failure['error']}" for failure in batch.failed_sheets
        )
        raise ModuleExecutionError(f"모든 시트의 VLM 구조 분석이 실패했습니다. {reasons}")

    def execute(
        self,
        input_data: LunaVlmStructureDetectorInputDTO,
        config: Optional[LunaVlmStructureDetectorConfigDTO] = None,
    ) -> Dict[str, Any]:
        """
        Analyze the selected workbook's visible sheets and assemble detected table structures.

        Parameters:
                payload (BaseModel): Execution settings containing the workbook name, expected hash, selected sheets, and detector configuration.

        Returns:
                Dict[str, Any]: A mapping containing the workbook name, verified hash, selected sheet names, assembled tables, and per-sheet failures.

        Raises:
                ModuleExecutionError: If the workbook cannot be resolved, has changed since selection, no sheets can be analyzed, or all sheet analyses fail.
        """
        cfg = config or LunaVlmStructureDetectorConfigDTO()
        workbook_path = self.catalog.resolve(input_data.file_name)
        current_hash = self.catalog.sha256(workbook_path)
        if current_hash != input_data.workbook_hash:
            raise ModuleExecutionError(
                "선택 이후 Excel 파일이 변경되었습니다. 파일 선택 모듈을 다시 실행하세요"
            )

        formula_workbook = None
        value_workbook = None
        batch: Optional[SheetAnalysisBatch] = None
        try:
            options = {
                "read_only": False,
                "keep_vba": workbook_path.suffix.lower() == ".xlsm",
            }
            formula_workbook = openpyxl.load_workbook(workbook_path, data_only=False, **options)
            value_workbook = openpyxl.load_workbook(workbook_path, data_only=True, **options)
            output_root = self.artifact_dir / current_hash[:16]
            prepared_sheets, preparation_failures = self._prepare_sheets(
                formula_workbook,
                value_workbook,
                input_data.sheet_names,
                output_root,
                cfg,
            )
            batch = self._analyze_prepared_sheets(
                cfg,
                prepared_sheets,
                preparation_failures,
                len(input_data.sheet_names),
            )
            self.last_usage = batch.usage
            self.last_model = cfg.model
            self.last_duration_seconds = batch.latency_seconds
            self._ensure_analysis_succeeded(batch, len(input_data.sheet_names))
        finally:
            if formula_workbook is not None:
                formula_workbook.close()
            if value_workbook is not None:
                value_workbook.close()

        assert batch is not None
        return {
            "file_name": workbook_path.name,
            "workbook_hash": current_hash,
            "sheet_names": input_data.sheet_names,
            "tables": [
                table
                for sheet_name in input_data.sheet_names
                for table in batch.tables_by_sheet.get(sheet_name, [])
            ],
            "failed_sheets": batch.failed_sheets,
        }


# ==============================================================================
# 5. Exports
# ==============================================================================
__all__ = [
    "LUNA_SHEET_RESPONSE_SCHEMA",
    "LUNA_VLM_SYSTEM_PROMPT",
    "LUNA_VLM_USER_TEMPLATE",
    "ClassifiedRegionDTO",
    "ClassifiedTableDTO",
    "ColumnHeaderNodeDTO",
    "LunaVisionClient",
    "LunaVlmStructureDetectorConfigDTO",
    "LunaVlmStructureDetectorExecutionDTO",
    "LunaVlmStructureDetectorInputDTO",
    "LunaVlmStructureDetectorModule",
    "LunaVlmStructureDetectorOutput",
    "SpreadsheetStructureOutput",
    "_safe_name",
]
