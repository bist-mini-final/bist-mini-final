from __future__ import annotations

from typing import List, Literal, Tuple

from pydantic import Field

from .base import ModuleDTO


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
    confidence: float
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
    tables: List[ClassifiedTableDTO]
