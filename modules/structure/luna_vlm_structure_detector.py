"""Exhaustive whole-sheet table structure analysis with GPT-5.6 Luna vision."""

from __future__ import annotations

import json
import logging
import concurrent.futures
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Protocol, Tuple, cast

logger = logging.getLogger(__name__)

import openpyxl
from pydantic import BaseModel, Field, model_validator

from backend.core.settings import PROCESSED_DATA_DIR, SPREADSHEET_ARTIFACT_DIR
from backend.providers.vision.openai_responses import (
    OpenAIResponsesVisionClient,
    OpenAIResponsesVisionError,
    OpenAIResponsesVisionResult,
)
from backend.storage.spreadsheets.cell_semantics import collect_non_empty_cells, compact_sheet_context
from backend.storage.spreadsheets.cell_type_overlay import render_cell_type_overlay
from backend.storage.spreadsheets.cell_visibility import WorksheetVisibility, worksheet_visible
from backend.storage.spreadsheets.prompt_guidance import (
    LEGACY_TEXT_CELL_ROLE_GUIDANCE,
    TABLE_UNIFICATION_GUIDANCE,
    TEXT_CELL_ROLE_GUIDANCE,
)
from backend.storage.spreadsheets.grid_structure import build_column_header_tree
from backend.storage.spreadsheets.sheet_renderer import ExcelSheetRenderer
from backend.storage.spreadsheets.table_fragment_merge import parse_excel_range
from backend.storage.spreadsheets.table_geometry import CellBounds, SheetLayout, cell_bounds_bbox
from backend.storage.spreadsheets.workbook_catalog import WorkbookCatalog, WorkbookCatalogError
from modules.common.base_module import (
    BaseModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleDTO,
    ModuleExecutionError,
    ModuleTaskPolicy,
)
from modules.structure.docling_table_detector import _safe_name
from modules.storage.processed_file_selector import WorkbookSelectionDTO
from modules.structure.spreadsheet_structure import SpreadsheetStructureOutput
from openpyxl.utils.cell import range_boundaries


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
    def complete_structured(
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
    ) -> OpenAIResponsesVisionResult | str: ...


class LunaVlmStructureDetectorInputDTO(WorkbookSelectionDTO):
    """Workbook identity and visible sheet selection."""


from modules.common.config import (
    DEFAULT_STRUCTURE_MAX_COLUMNS,
    DEFAULT_STRUCTURE_MAX_OUTPUT_TOKENS,
    DEFAULT_STRUCTURE_MAX_ROWS,
    DEFAULT_VLM_MODEL,
    DEFAULT_VLM_TIMEOUT_SECONDS,
)


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
        default=50000,
        ge=100,
        le=100000,
        description="한 시트에서 좌표 컨텍스트로 전달할 최대 값 셀 수",
    )
    reasoning_effort: Literal["none", "low", "medium", "high"] = Field(
        default="low",
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
    validation_retries: int = Field(default=1, ge=0, le=2, description="좌표 규칙 위반 응답의 교정 재시도 횟수")
    max_concurrency: int = Field(
        default=4,
        ge=1,
        le=16,
        description="동시에 실행할 시트별 VLM 요청 수",
    )
    system_prompt: str = Field(default=LUNA_VLM_SYSTEM_PROMPT, min_length=1, description="전체 시트 구조 식별 시스템 프롬프트")
    user_prompt_template: str = Field(
        default=LUNA_VLM_USER_TEMPLATE,
        min_length=1,
        description="sheet_name, sheet_range, sheet_context 변수를 지원하는 전체 시트 프롬프트",
    )


class LunaVlmStructureDetectorExecutionDTO(
    LunaVlmStructureDetectorInputDTO,
    LunaVlmStructureDetectorConfigDTO,
):
    """Internal union with legacy workflow migration support."""

    @model_validator(mode="before")
    @classmethod
    def discard_legacy_tiling_settings(cls, value: Any) -> Any:
        """Accept workflows saved before whole-sheet inference replaced tiling."""

        if not isinstance(value, dict):
            return value
        migrated = dict(value)
        for field_name in (
            "tile_rows",
            "tile_columns",
            "row_overlap",
            "column_overlap",
            "overview_max_edge",
        ):
            migrated.pop(field_name, None)
        legacy_system_prompt = migrated.get("system_prompt")
        if (
            isinstance(legacy_system_prompt, str)
            and LEGACY_TEXT_CELL_ROLE_GUIDANCE in legacy_system_prompt
            and TEXT_CELL_ROLE_GUIDANCE not in legacy_system_prompt
        ):
            migrated["system_prompt"] = legacy_system_prompt.replace(
                LEGACY_TEXT_CELL_ROLE_GUIDANCE,
                TEXT_CELL_ROLE_GUIDANCE,
            )
            legacy_system_prompt = migrated["system_prompt"]
        if (
            isinstance(legacy_system_prompt, str)
            and "You receive two images in this order" in legacy_system_prompt
            and "current tile" in legacy_system_prompt
        ):
            migrated.pop("system_prompt", None)
        legacy_user_prompt = migrated.get("user_prompt_template")
        if (
            isinstance(legacy_user_prompt, str)
            and "{tile_index}" in legacy_user_prompt
            and "{tile_context}" in legacy_user_prompt
        ):
            migrated.pop("user_prompt_template", None)
        return migrated


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
    if None in (min_column, min_row, max_column, max_row):
        raise ModuleExecutionError(f"VLM {field_name}은 셀 사각형 범위여야 합니다: {value}")
    return CellBounds(int(min_row), int(max_row), int(min_column), int(max_column))


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
        row
        for row in range(bounds.min_row, bounds.max_row + 1)
        if not visibility.row_hidden(row)
    ]
    columns = [
        column
        for column in range(bounds.min_column, bounds.max_column + 1)
        if not visibility.column_hidden(column)
    ]
    if not rows or not columns:
        raise ModuleExecutionError(
            f"VLM {field_name}에 표시된 셀이 없습니다: {bounds.excel_range}"
        )
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
            header_bounds = _bounds(table.column_header_range, "column_header_range") if table.column_header_range else None
            title_bounds = _bounds(table.title_range, "title_range") if table.title_range else None
            row_bounds = _bounds(table.row_header_range, "row_header_range") if table.row_header_range else None
            parsed_tables.append((table, excel_bounds, data_bounds, header_bounds, title_bounds, row_bounds))
        except ModuleExecutionError:
            return tables

    first_data = parsed_tables[0][2]
    all_same_columns = all(
        item[2].min_column == first_data.min_column and item[2].max_column == first_data.max_column
        for item in parsed_tables
    )

    if all_same_columns:
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
            unified_row_header = CellBounds(min_data_row, max_data_row, min_r_col, max_r_col).excel_range
        else:
            unified_row_header = None

        return [
            VlmTableDecisionDTO(
                excel_range=CellBounds(min_whole_row, max_whole_row, min_whole_col, max_whole_col).excel_range,
                title_range=primary_title.excel_range if primary_title else None,
                column_header_range=primary_header.excel_range if primary_header else None,
                row_header_range=unified_row_header,
                data_range=CellBounds(min_data_row, max_data_row, first_data.min_column, first_data.max_column).excel_range,
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
    whole = parse_excel_range(table.excel_range)
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
        if value and not _contains(whole, parse_excel_range(value)):
            raise ModuleExecutionError(
                f"Luna {field_name}이 excel_range를 벗어났습니다: {value}"
            )
    return table


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
    execution_model = LunaVlmStructureDetectorExecutionDTO
    output_model = LunaVlmStructureDetectorOutput

    def __init__(
        self,
        vision_client: Optional[LunaVisionClient] = None,
        catalog: Optional[WorkbookCatalog] = None,
        renderer: Optional[ExcelSheetRenderer] = None,
        processed_dir: Path = PROCESSED_DATA_DIR,
        artifact_dir: Path = SPREADSHEET_ARTIFACT_DIR,
    ) -> None:
        self.vision_client = vision_client or OpenAIResponsesVisionClient()
        self.catalog = catalog or WorkbookCatalog(processed_dir)
        self.renderer = renderer or ExcelSheetRenderer()
        self.artifact_dir = artifact_dir
        self.structure_assembler = self

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
        layout,
        visibility: WorksheetVisibility,
    ) -> Dict[str, CellBounds | None]:
        named = {
            "excel_range": _bounds(table.excel_range, "excel_range"),
            "title_range": _bounds(table.title_range, "title_range") if table.title_range else None,
            "column_header_range": _bounds(table.column_header_range, "column_header_range") if table.column_header_range else None,
            "row_header_range": _bounds(table.row_header_range, "row_header_range") if table.row_header_range else None,
            "data_range": _bounds(table.data_range, "data_range"),
        }
        whole = cast(CellBounds, named["excel_range"])
        data = cast(CellBounds, named["data_range"])
        sheet = CellBounds(1, layout.max_row, 1, layout.max_column)
        if not _contains(sheet, whole):
            raise ModuleExecutionError(f"VLM 테이블 범위가 분석 시트를 벗어났습니다: {whole.excel_range}")
        for field_name, bounds in named.items():
            if field_name == "excel_range" or bounds is None:
                continue
            if not _contains(whole, bounds):
                raise ModuleExecutionError(f"VLM {field_name}이 테이블 범위를 벗어났습니다: {bounds.excel_range}")
        named = {
            field_name: (
                _visible_bounds(bounds, visibility, field_name)
                if bounds is not None
                else None
            )
            for field_name, bounds in named.items()
        }
        whole = cast(CellBounds, named["excel_range"])
        data = cast(CellBounds, named["data_range"])
        title = cast(Optional[CellBounds], named["title_range"])
        column_header = cast(Optional[CellBounds], named["column_header_range"])
        row_header = cast(Optional[CellBounds], named["row_header_range"])

        if title and column_header:
            if title.max_row >= column_header.min_row:
                if title.min_row < column_header.min_row:
                    title = CellBounds(
                        title.min_row,
                        column_header.min_row - 1,
                        title.min_column,
                        title.max_column,
                    )
                else:
                    title = None
                named["title_range"] = title

        header_bottom = None
        if column_header:
            header_bottom = column_header.max_row
        elif title:
            header_bottom = title.max_row

        if header_bottom is not None and header_bottom >= data.min_row:
            if data.max_row > header_bottom:
                data = CellBounds(
                    header_bottom + 1,
                    data.max_row,
                    data.min_column,
                    data.max_column,
                )
                named["data_range"] = data
            else:
                if column_header and column_header.min_row < data.min_row:
                    column_header = CellBounds(
                        column_header.min_row,
                        data.min_row - 1,
                        column_header.min_column,
                        column_header.max_column,
                    )
                    named["column_header_range"] = column_header
                else:
                    column_header = None
                    named["column_header_range"] = None
                if title and title.max_row >= data.min_row:
                    if title.min_row < data.min_row:
                        title = CellBounds(
                            title.min_row,
                            data.min_row - 1,
                            title.min_column,
                            title.max_column,
                        )
                    else:
                        title = None
                    named["title_range"] = title

        if title and title.max_row >= data.min_row:
            if title.min_row < data.min_row:
                title = CellBounds(
                    title.min_row,
                    data.min_row - 1,
                    title.min_column,
                    title.max_column,
                )
            else:
                title = None
            named["title_range"] = title

        if column_header and column_header.max_row >= data.min_row:
            if column_header.min_row < data.min_row:
                column_header = CellBounds(
                    column_header.min_row,
                    data.min_row - 1,
                    column_header.min_column,
                    column_header.max_column,
                )
            else:
                column_header = None
            named["column_header_range"] = column_header

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
                named["data_range"] = data
            else:
                row_header = None
            named["row_header_range"] = row_header
        if row_header:
            row_header = CellBounds(
                data.min_row,
                data.max_row,
                row_header.min_column,
                row_header.max_column,
            )
            named["row_header_range"] = row_header
        if column_header:
            column_header = CellBounds(
                column_header.min_row,
                data.min_row - 1,
                data.min_column,
                data.max_column,
            )
            named["column_header_range"] = column_header
        return named

    def _table_output(
        self,
        table_index: int,
        table: VlmTableDecisionDTO,
        worksheet,
        layout,
    ) -> Dict[str, Any]:
        visibility = WorksheetVisibility.from_worksheet(worksheet)
        named = self._validate_table(table, layout, visibility)
        whole = cast(CellBounds, named["excel_range"])
        data = cast(CellBounds, named["data_range"])
        prefix = f"table_{table_index}"
        regions: List[Dict[str, Any]] = []
        parents: List[str] = []

        for key, region_type in (
            ("title_range", "title"),
            ("column_header_range", "column_header"),
        ):
            bounds = cast(Optional[CellBounds], named[key])
            if bounds is None:
                continue
            region_id = f"{prefix}_{region_type}"
            regions.append(self._region(region_id, region_type, bounds, layout, list(parents)))
            parents.append(region_id)

        row_header = cast(Optional[CellBounds], named["row_header_range"])
        if row_header is not None:
            row_header_id = f"{prefix}_row_header"
            regions.append(self._region(row_header_id, "row_header", row_header, layout, list(parents)))
            parents.append(row_header_id)
        regions.append(self._region(f"{prefix}_data", "data", data, layout, list(parents)))

        column_header = cast(Optional[CellBounds], named["column_header_range"])
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
        settings: LunaVlmStructureDetectorExecutionDTO,
        sheet_name: str,
        sheet_bounds: CellBounds,
        image_path: Path,
        layout: SheetLayout,
        visibility: WorksheetVisibility,
        cells: List[Dict[str, Any]],
    ) -> List[LocalVlmTableDecisionDTO]:
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
                response = self.vision_client.complete_structured(
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
                previous_response = (
                    response.content
                    if isinstance(response, OpenAIResponsesVisionResult)
                    else str(response)
                )
                decision = LunaSheetDecisionDTO.model_validate_json(previous_response)
                unified_tables = unify_sheet_tables(decision.tables)
                tables = [
                    _validated_sheet_decision(table, sheet_bounds)
                    for table in unified_tables
                ]
                for table in tables:
                    self.structure_assembler._validate_table(table, layout, visibility)
                return tables
            except OpenAIResponsesVisionError:
                raise
            except (ValueError, TypeError, json.JSONDecodeError, ModuleExecutionError) as error:
                validation_error = str(error)
                if attempt >= settings.validation_retries:
                    raise ModuleExecutionError(
                        f"Luna 시트 {sheet_name} 응답을 좌표 규칙에 맞게 교정하지 못했습니다: {validation_error}"
                    ) from error
        return []

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        """
        Analyze the selected workbook's visible sheets and assemble detected table structures.
        
        Parameters:
        	payload (BaseModel): Execution settings containing the workbook name, expected hash, selected sheets, and detector configuration.
        
        Returns:
        	Dict[str, Any]: A mapping containing the workbook name, verified hash, selected sheet names, assembled tables, and per-sheet failures.
        
        Raises:
        	ModuleExecutionError: If the workbook cannot be resolved, has changed since selection, no sheets can be analyzed, or all sheet analyses fail.
        """
        settings = cast(LunaVlmStructureDetectorExecutionDTO, payload)
        try:
            workbook_path = self.catalog.resolve(settings.file_name)
            current_hash = self.catalog.sha256(workbook_path)
        except (OSError, ValueError, WorkbookCatalogError) as error:
            raise ModuleExecutionError(str(error)) from error
        if current_hash != settings.workbook_hash:
            raise ModuleExecutionError("선택 이후 Excel 파일이 변경되었습니다. 파일 선택 모듈을 다시 실행하세요")

        formula_workbook = None
        value_workbook = None
        try:
            options = {
                "read_only": False,
                "keep_vba": workbook_path.suffix.lower() == ".xlsm",
            }
            formula_workbook = openpyxl.load_workbook(workbook_path, data_only=False, **options)
            value_workbook = openpyxl.load_workbook(workbook_path, data_only=True, **options)
            outputs: List[Dict[str, Any]] = []
            failed_sheets: List[Dict[str, str]] = []
            analyzed_sheet_count = 0
            output_root = self.artifact_dir / current_hash[:16]

            # Phase 1: Render and extract geometry on the main thread (openpyxl is not thread-safe)
            prepared_sheets: List[Dict[str, Any]] = []
            for sheet_name in settings.sheet_names:
                if sheet_name not in formula_workbook.sheetnames:
                    logger.warning("[Luna VLM] Excel 시트를 찾을 수 없어 건너뜁니다: %s", sheet_name)
                    failed_sheets.append({"sheet_name": sheet_name, "error": "시트를 찾을 수 없습니다"})
                    continue
                formula_sheet = formula_workbook[sheet_name]
                value_sheet = value_workbook[sheet_name]
                if not worksheet_visible(formula_sheet) or not worksheet_visible(value_sheet):
                    logger.info("[Luna VLM] 숨겨진 시트 건너뜀: %s", sheet_name)
                    failed_sheets.append({"sheet_name": sheet_name, "error": "숨겨진 시트입니다"})
                    continue

                try:
                    safe_sheet = _safe_name(sheet_name)
                    rendered_path = output_root / "rendered" / f"{safe_sheet}.png"
                    typed_path = output_root / "typed" / f"{safe_sheet}.png"
                    layout = self.renderer.render(
                        value_sheet,
                        rendered_path,
                        settings.max_rows,
                        settings.max_columns,
                    )
                    cells = collect_non_empty_cells(
                        formula_sheet,
                        value_sheet,
                        layout,
                        settings.max_context_cells,
                    )

                    render_cell_type_overlay(rendered_path, typed_path, layout, cells)
                    visible_rows = [row for row, height in enumerate(layout.row_heights, start=1) if height > 0]
                    visible_columns = [column for column, width in enumerate(layout.column_widths, start=1) if width > 0]
                    if not visible_rows or not visible_columns or not cells:
                        logger.warning("[Luna VLM] 시트 %s에 표시된 셀이 없어 건너뜁니다.", sheet_name)
                        failed_sheets.append({"sheet_name": sheet_name, "error": "표시된 데이터 셀이 없습니다"})
                        continue

                    sheet_bounds = CellBounds(
                        visible_rows[0],
                        visible_rows[-1],
                        visible_columns[0],
                        visible_columns[-1],
                    )
                    visibility = WorksheetVisibility.from_worksheet(value_sheet)
                    prepared_sheets.append({
                        "sheet_name": sheet_name,
                        "sheet_bounds": sheet_bounds,
                        "typed_path": typed_path,
                        "layout": layout,
                        "visibility": visibility,
                        "cells": cells,
                        "value_sheet": value_sheet,
                    })
                    print(f"[Luna VLM] 시트 '{sheet_name}' 사전 렌더링 완료 ({len(cells)}개 셀)", flush=True)
                except Exception as prep_err:
                    logger.exception("[Luna VLM] 시트 '%s' 사전 렌더링 실패", sheet_name)
                    failed_sheets.append({"sheet_name": sheet_name, "error": str(prep_err)})
                    continue

            # Phase 2: Parallel OpenAI Vision API calls (pure I/O, completely thread-safe)
            if not prepared_sheets:
                reasons = "; ".join(
                    f"{failure['sheet_name']}: {failure['error']}"
                    for failure in failed_sheets
                )
                raise ModuleExecutionError(
                    f"분석 가능한 시트가 없습니다. {reasons or '선택된 시트가 비어 있습니다'}"
                )

            def _call_vlm(ctx: Dict[str, Any]) -> Tuple[Dict[str, Any], List[LocalVlmTableDecisionDTO]]:
                """
                Analyze a prepared worksheet with the vision-language model.
                
                Parameters:
                    ctx (Dict[str, Any]): Prepared worksheet context, including the sheet name, bounds, typed cell path, layout, visibility, and cell metadata.
                
                Returns:
                    Tuple[Dict[str, Any], List[LocalVlmTableDecisionDTO]]: The original worksheet context and the detected table decisions.
                """
                print(f"[Luna VLM] 시트 '{ctx['sheet_name']}' OpenAI VLM 호출 시작...", flush=True)
                decisions = self._analyze_sheet(
                    settings,
                    ctx["sheet_name"],
                    ctx["sheet_bounds"],
                    ctx["typed_path"],
                    ctx["layout"],
                    ctx["visibility"],
                    ctx["cells"],
                )
                print(f"[Luna VLM] 시트 '{ctx['sheet_name']}' OpenAI VLM 응답 완료 ({len(decisions)}개 표 감지)", flush=True)
                return ctx, decisions

            max_workers = min(settings.max_concurrency, len(prepared_sheets)) or 1
            print(f"[Luna VLM] {len(prepared_sheets)}개 시트 병렬 VLM 분석 시작 (스레드 {max_workers}개)...", flush=True)
            self.report_progress(
                {
                    "phase": "sheet_analysis",
                    "completed_sheets": 0,
                    "failed_sheets": len(failed_sheets),
                    "total_sheets": len(settings.sheet_names),
                    "active_sheets": [
                        str(context["sheet_name"])
                        for context in prepared_sheets
                    ],
                }
            )
            tables_by_sheet: Dict[str, List[Dict[str, Any]]] = {}
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(_call_vlm, ctx): ctx
                    for ctx in prepared_sheets
                }
                for future in concurrent.futures.as_completed(futures):
                    try:
                        ctx, decisions = future.result()
                        s_name = ctx["sheet_name"]
                        v_sheet = ctx["value_sheet"]
                        s_layout = ctx["layout"]
                        sheet_tables = []
                        for table_index, decision in enumerate(decisions, start=1):
                            table_out = self.structure_assembler._table_output(
                                table_index,
                                decision,
                                v_sheet,
                                s_layout,
                            )
                            table_out["sheet_name"] = s_name
                            sheet_tables.append(table_out)
                        tables_by_sheet[s_name] = sheet_tables
                        analyzed_sheet_count += 1
                        print(f"[Luna VLM] 시트 '{s_name}' 테이블 {len(sheet_tables)}개 최종 조립 완료", flush=True)
                    except Exception as future_err:
                        failed_ctx = futures[future]
                        failed_name = str(failed_ctx["sheet_name"])
                        logger.exception("[Luna VLM] 시트 '%s' 분석 중 예외 발생", failed_name)
                        failed_sheets.append({"sheet_name": failed_name, "error": str(future_err)})
                        print(f"[Luna VLM] 시트 분석 중 예외: {future_err}", flush=True)
                    finally:
                        self.report_progress(
                            {
                                "phase": "sheet_analysis",
                                "completed_sheets": analyzed_sheet_count,
                                "failed_sheets": len(failed_sheets),
                                "total_sheets": len(settings.sheet_names),
                                "finished_sheets": analyzed_sheet_count
                                + len(failed_sheets),
                            }
                        )

            outputs = [
                table
                for sheet_name in settings.sheet_names
                for table in tables_by_sheet.get(sheet_name, [])
            ]

            self.report_progress(
                {
                    "phase": "sheet_analysis",
                    "completed_sheets": analyzed_sheet_count,
                    "failed_sheets": len(failed_sheets),
                    "total_sheets": len(settings.sheet_names),
                }
            )
            if analyzed_sheet_count == 0:
                reasons = "; ".join(
                    f"{failure['sheet_name']}: {failure['error']}"
                    for failure in failed_sheets
                )
                raise ModuleExecutionError(f"모든 시트의 VLM 구조 분석이 실패했습니다. {reasons}")
        finally:
            if formula_workbook is not None:
                formula_workbook.close()
            if value_workbook is not None:
                value_workbook.close()

        return {
            "file_name": workbook_path.name,
            "workbook_hash": current_hash,
            "sheet_names": settings.sheet_names,
            "tables": outputs,
            "failed_sheets": failed_sheets,
        }
