"""Shared semantic guidance for spreadsheet structure prompts."""


TEXT_CELL_ROLE_GUIDANCE = """Cell-role guidance:
- Ordinary descriptive text is strong structural evidence. Text-dominant rows above a numeric/date/formula matrix are usually titles or column headers, and text-dominant columns to its left are usually row headers. Prefer those header roles unless position, repetition, or surrounding layout clearly shows that the text belongs to the data matrix.
- A text-typed cell is not automatically a header. Missing-value and status literals such as `NA`, `N/A`, `NM`, `N.M.`, `N/M`, `-`, `--`, `—`, `not available`, and `not meaningful` are data values when they occupy a data-matrix position. Keep them inside data_range and never widen a header range merely because these values are represented as text.
- Free-form text may also be legitimate table data. Resolve ambiguous cells from spatial continuity, neighboring value roles, merged cells, repetition, and formatting; use the value type only as a strong hint."""

TABLE_UNIFICATION_GUIDANCE = """Financial statement & table boundary guidance:
- Financial worksheets (such as Income Statement, Balance Sheet, Cash Flow, Key Stats) typically contain multiple vertical sections (e.g. Revenue, Operating Expenses, Non-Operating Items, Tax, Supplemental Items, Ratios) that share the same top period/date column headers (e.g. Fiscal Year Ended, FY2014...FY2024, LTM, quarterly/annual dates).
- You MUST treat all vertically stacked sections sharing the same column timeline as ONE SINGLE UNIFIED TABLE.
- Do NOT split the worksheet into multiple small tables at blank rows, intermediate section headers, category divider titles, or summary rows.
- The `column_header_range` must point to the top period/date header rows (e.g. row 3-4) and `data_range` must encompass all data rows down to the end of the sheet, so every data cell inherits its respective column header (period date).
- Only emit multiple tables if there are genuinely independent side-by-side tables with different column structures."""
