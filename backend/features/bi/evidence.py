"""Validation helpers for source cells admitted into BI evidence."""

from __future__ import annotations

from typing import Protocol, TypeVar

from backend.storage.spreadsheets.structured_cell_text import (
    extract_resolved_cell_value,
)


class SourceCell(Protocol):
    """Structural evidence contract shared by retrieval and snapshot models."""

    source_text: str


SourceCellT = TypeVar("SourceCellT", bound=SourceCell)


def source_cell_value(source_text: str) -> str | None:
    """Return the structured cell value, or ``None`` for absent placeholders."""

    return extract_resolved_cell_value(source_text)


def is_verifiable_cell(cell: SourceCell) -> bool:
    """Whether a context cell contains a concrete value suitable for evidence."""

    return source_cell_value(cell.source_text) is not None


def verifiable_cells(cells: tuple[SourceCellT, ...]) -> tuple[SourceCellT, ...]:
    """Filter placeholder and malformed cells while preserving retrieval order."""

    return tuple(cell for cell in cells if is_verifiable_cell(cell))


__all__ = [
    "SourceCell",
    "is_verifiable_cell",
    "source_cell_value",
    "verifiable_cells",
]
