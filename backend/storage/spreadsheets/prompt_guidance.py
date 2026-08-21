"""Shared semantic guidance for spreadsheet structure prompts."""


LEGACY_TEXT_CELL_ROLE_GUIDANCE = """Cell-role guidance:
- Ordinary descriptive text is strong structural evidence. Text-dominant rows above a numeric/date/formula matrix are usually titles or column headers, and text-dominant columns to its left are usually row headers. Prefer those header roles unless position, repetition, or surrounding layout clearly shows that the text belongs to the data matrix.
- A text-typed cell is not automatically a header. Missing-value and status literals such as `NA`, `N/A`, `NM`, `N.M.`, `N/M`, `-`, `--`, `—`, `not available`, and `not meaningful` are data values when they occupy a data-matrix position. Keep them inside data_range and never widen a header range merely because these values are represented as text.
- Free-form text may also be legitimate table data. Resolve ambiguous cells from spatial continuity, neighboring value roles, merged cells, repetition, and formatting; use the value type only as a strong hint."""


TEXT_CELL_ROLE_GUIDANCE = """Cell-role guidance:
- Determine a cell's role from the table topology and header semantics, never from its value type alone.
- Distinguish record tables from matrix/crosstab tables before assigning row headers:
  - A record table has one header row of peer field names such as `NAME`, `ROLE`, `AGE`, `COUNTRY`, `DESCRIPTION`, `DATE`, or `SALARY`, followed by repeated entity records. Every column below those field names belongs to data_range, including leading text columns. Set row_header_range to null; column_header_range and data_range must span the same field columns.
  - A matrix/crosstab has left-side cells that name metrics or row categories while the columns represent repeated measures, periods, scenarios, or comparable dimensions. Only in this layout should those left-side label columns become row_header_range.
- Never classify leading text columns as row headers merely because numeric/date/formula columns appear to their right. A peer field header above a text column is strong evidence that the text below is data.
- Text-dominant rows above a matrix/crosstab are usually titles or column headers. Text-dominant columns to its left are usually row headers only when the matrix/crosstab relationship is present.
- A text-typed cell is not automatically a header. Missing-value and status literals such as `NA`, `N/A`, `NM`, `N.M.`, `N/M`, `-`, `--`, `—`, `not available`, and `not meaningful` are data values when they occupy a data-matrix position. Keep them inside data_range and never widen a header range merely because these values are represented as text.
- Free-form text may also be legitimate table data. Resolve ambiguous cells from spatial continuity, neighboring value roles, merged cells, repetition, and formatting; use the value type only as a hint."""

TABLE_UNIFICATION_GUIDANCE = """Table boundary & multi-section guidance:
- Vertically stacked sections that share the exact same top column headers and column timeline must be treated as ONE SINGLE UNIFIED TABLE. Do not split them at blank rows, intermediate subheadings, or subtotal rows when they share the same column header alignment.
- Conversely, when vertical or horizontal blocks in a worksheet have DIFFERENT column structures, distinct header rows, differing column counts, or independent timeline semantics, you MUST split them into separate, independent rectangular tables.
- A table's `column_header_range` must accurately cover only the columns relevant to its own `data_range`, and its `data_range` must strictly contain data cells that belong to those headers."""
