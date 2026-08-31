"""Spreadsheet cell visibility rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet

from openpyxl.utils import column_index_from_string


@dataclass(frozen=True)
class WorksheetVisibility:
    """Snapshot the worksheet axes that must never be read or rendered."""

    hidden_rows: FrozenSet[int]
    hidden_columns: FrozenSet[int]

    @classmethod
    def from_worksheet(cls, worksheet) -> "WorksheetVisibility":
        hidden_rows = frozenset(
            int(row)
            for row, dimension in worksheet.row_dimensions.items()
            if dimension.hidden or dimension.height == 0
        )
        hidden_columns: set[int] = set()
        for key, dimension in worksheet.column_dimensions.items():
            if not (dimension.hidden or dimension.width == 0):
                continue
            if dimension.min is None or dimension.max is None:
                column = column_index_from_string(str(key))
                hidden_columns.add(column)
            else:
                hidden_columns.update(
                    range(int(dimension.min), int(dimension.max) + 1)
                )
        return cls(hidden_rows, frozenset(hidden_columns))

    def row_hidden(self, row: int) -> bool:
        return row in self.hidden_rows

    def column_hidden(self, column: int) -> bool:
        return column in self.hidden_columns

    def cell_visible(self, row: int, column: int) -> bool:
        return row not in self.hidden_rows and column not in self.hidden_columns


def worksheet_visible(worksheet) -> bool:
    """A hidden sheet follows the same exclusion rule as hidden cells."""

    return getattr(worksheet, "sheet_state", "visible") == "visible"
