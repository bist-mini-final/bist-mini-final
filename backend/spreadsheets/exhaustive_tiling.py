"""Exhaustive visible-grid tiling for spreadsheet vision models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from PIL import Image

from .table_geometry import CellBounds, SheetLayout, cell_bounds_bbox


@dataclass(frozen=True)
class SpreadsheetTile:
    tile_id: str
    row_index: int
    column_index: int
    bounds: CellBounds
    visible_rows: Tuple[int, ...]
    visible_columns: Tuple[int, ...]
    pixel_bbox: Tuple[float, ...]


def _axis_chunks(
    visible_indices: Sequence[int],
    chunk_size: int,
    overlap: int,
) -> List[Tuple[int, ...]]:
    if chunk_size < 1:
        raise ValueError("타일 크기는 1 이상이어야 합니다")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("타일 겹침은 0 이상이고 타일 크기보다 작아야 합니다")
    if not visible_indices:
        return []

    chunks: List[Tuple[int, ...]] = []
    start = 0
    stride = chunk_size - overlap
    while start < len(visible_indices):
        chunk = tuple(visible_indices[start : start + chunk_size])
        chunks.append(chunk)
        if start + chunk_size >= len(visible_indices):
            break
        start += stride
    return chunks


def build_exhaustive_tiles(
    layout: SheetLayout,
    tile_rows: int,
    tile_columns: int,
    row_overlap: int,
    column_overlap: int,
) -> List[SpreadsheetTile]:
    """Cover every visible row/column pair without using table candidates."""

    visible_rows = [
        row
        for row, height in enumerate(layout.row_heights, start=1)
        if height > 0
    ]
    visible_columns = [
        column
        for column, width in enumerate(layout.column_widths, start=1)
        if width > 0
    ]
    row_chunks = _axis_chunks(visible_rows, tile_rows, row_overlap)
    column_chunks = _axis_chunks(visible_columns, tile_columns, column_overlap)
    tiles: List[SpreadsheetTile] = []
    for row_index, rows in enumerate(row_chunks, start=1):
        for column_index, columns in enumerate(column_chunks, start=1):
            bounds = CellBounds(rows[0], rows[-1], columns[0], columns[-1])
            tiles.append(
                SpreadsheetTile(
                    tile_id=f"r{row_index:03d}-c{column_index:03d}",
                    row_index=row_index,
                    column_index=column_index,
                    bounds=bounds,
                    visible_rows=rows,
                    visible_columns=columns,
                    pixel_bbox=cell_bounds_bbox(bounds, layout),
                )
            )
    return tiles


def tile_context(
    sheet_name: str,
    tile: SpreadsheetTile,
    cells: Iterable[Dict[str, Any]],
) -> Dict[str, Any]:
    """Return exact cell facts for one tile, excluding hidden axes by construction."""

    visible_rows = set(tile.visible_rows)
    visible_columns = set(tile.visible_columns)
    selected = [
        cell
        for cell in cells
        if int(cell["row"]) in visible_rows
        and int(cell["column"]) in visible_columns
    ]
    rows: Dict[int, List[List[Any]]] = {}
    for cell in selected:
        flags = {
            key: cell[key]
            for key in ("is_formula", "formula", "merged_range")
            if key in cell
        }
        item: List[Any] = [cell["coord"], cell["type"], cell["value"]]
        if flags:
            item.append(flags)
        rows.setdefault(int(cell["row"]), []).append(item)
    return {
        "sheet_name": sheet_name,
        "tile_id": tile.tile_id,
        "tile_range": tile.bounds.excel_range,
        "visible_rows": list(tile.visible_rows),
        "visible_columns": list(tile.visible_columns),
        "cell_count": len(selected),
        "cell_tuple": ["excel_coord", "value_type", "value", "optional_flags"],
        "rows": [
            {"row": row, "cells": row_cells}
            for row, row_cells in sorted(rows.items())
        ],
    }


def render_overview(source_path: Path, output_path: Path, max_edge: int) -> None:
    """Create a low-cost whole-sheet overview without changing its aspect ratio."""

    with Image.open(source_path) as source:
        image = source.convert("RGB")
        image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path, format="PNG", optimize=True)


def render_tile(source_path: Path, output_path: Path, tile: SpreadsheetTile) -> None:
    """Crop one high-detail tile from the typed whole-sheet image."""

    x1, y1, x2, y2 = tile.pixel_bbox
    with Image.open(source_path) as source:
        crop = source.crop(
            (
                max(0, round(x1)),
                max(0, round(y1)),
                min(source.width, round(x2)),
                min(source.height, round(y2)),
            )
        ).convert("RGB")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        crop.save(output_path, format="PNG", optimize=True)
