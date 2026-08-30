"""Validation helpers for source cells admitted into BI evidence."""

from __future__ import annotations

from backend.storage.spreadsheets.structured_cell_text import (
    extract_resolved_cell_value,
)

from .extraction_models import BiContextCell


def source_cell_value(source_text: str) -> str | None:
    """Return the structured cell value, or ``None`` for absent placeholders."""

    return extract_resolved_cell_value(source_text)


def is_verifiable_cell(cell: BiContextCell) -> bool:
    """Whether a context cell contains a concrete value suitable for evidence."""

    return source_cell_value(cell.source_text) is not None


def verifiable_cells(cells: tuple[BiContextCell, ...]) -> tuple[BiContextCell, ...]:
    """Filter placeholder and malformed cells while preserving retrieval order."""

    return tuple(cell for cell in cells if is_verifiable_cell(cell))


__all__ = ["is_verifiable_cell", "source_cell_value", "verifiable_cells"]
