"""Shared semantic guidance for spreadsheet structure prompts."""


TEXT_CELL_ROLE_GUIDANCE = """Cell-role guidance:
- Ordinary descriptive text is strong structural evidence. Text-dominant rows above a numeric/date/formula matrix are usually titles or column headers, and text-dominant columns to its left are usually row headers. Prefer those header roles unless position, repetition, or surrounding layout clearly shows that the text belongs to the data matrix.
- A text-typed cell is not automatically a header. Missing-value and status literals such as `NA`, `N/A`, `NM`, `N.M.`, `N/M`, `-`, `--`, `—`, `not available`, and `not meaningful` are data values when they occupy a data-matrix position. Keep them inside data_range and never widen a header range merely because these values are represented as text.
- Free-form text may also be legitimate table data. Resolve ambiguous cells from spatial continuity, neighboring value roles, merged cells, repetition, and formatting; use the value type only as a strong hint."""
