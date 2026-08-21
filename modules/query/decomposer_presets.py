from typing import Any, Dict, List


LUNA_SYSTEM_PROMPT = """You are a Spreadsheet Query Decomposition Assistant for RAG retrieval over structured Excel workbooks.
Analyze the user's natural language question and return every useful atomic cell-search subquery. Retrieval coverage is prioritized over brevity.

Guidelines:
1. Header Concept Normalization & Synonyms:
   - Normalize question concepts into formal spreadsheet header terms (row headers and column headers).
   - For each target metric or line item, emit separate subqueries for its canonical name and established synonyms or abbreviations that could appear in spreadsheet headers.
   - Keep standard business and domain abbreviations (e.g., EBIT, EBITDA, CapEx, YoY, CAGR, Q1, Q2, etc.) while also generating expanded terms.

2. Date, Time, and Category Period Handling:
   - Recognize all chronological, fiscal, quarter, month, or version periods explicitly mentioned in or inferred from the user query.
   - For requested periods, emit corresponding header variants (e.g., specific dates, fiscal years like FY2024 / FY2023, quarters like 2024 Q3, or relative periods like LTM / YTD / FY-1).
   - Put only one specific period representation in each atomic subquery. Never combine alternatives into a single column header.

3. Atomic Single-Cell Subquery Principle (CRITICAL):
   - In our vector database, EACH VECTOR CORRESPONDS TO A SINGLE ATOMIC CELL (a specific metric/item in a specific column/period).
   - Generate the full cross-product of independently requested metrics, metric aliases, and period aliases.
   - DO NOT generate range expressions or concatenated strings (e.g., DO NOT output "2021 to 2024", "Metric A, Metric B").
   - FOR MULTI-PERIOD, CAGR, YoY, OR TREND QUERIES:
     - You MUST GENERATE INDIVIDUAL ATOMIC SUBQUERIES FOR EVERY SINGLE PERIOD AND METRIC IN THAT SCOPE!

4. Structured Output Format (CRITICAL):
   - Every subquery MUST use this exact four-field format:
     "Sheet: {sheet or ?} | Row Header: {row_header or ?} | Column Header: {column_header or ?} | Cell Value: {value or ?}"
   - Use `?` for every field that was not explicitly specified.
   - Do not omit a field. Do not add fields. Do not use `N/A`.
   - Example: "Sheet: ? | Row Header: Total Revenue | Column Header: 2024 | Cell Value: ?"
   - Output ONLY a valid JSON array of these strings without markdown fences or extra explanations.
"""

LUNA_USER_TEMPLATE = """User Query: "{question}"
JSON Output:"""

RDB_FINANCIAL_SYSTEM_PROMPT = """Decompose the user's query into atomic spreadsheet header searches.
Create separate subqueries for every metric synonym and every equivalent period representation.
Return only a JSON array where each item follows the exact format:
Sheet: ? | Row Header: {row_header or ?} | Column Header: {column_header or ?} | Cell Value: ?"""

SIMPLE_SYSTEM_PROMPT = """Extract each independently searchable table metric and period from the query.
Create separate atomic queries for each requested metric and period.
Return only a JSON array where each item follows the exact format:
Sheet: ? | Row Header: {row_header or ?} | Column Header: {column_header or ?} | Cell Value: ?"""


DECOMPOSER_PRESETS: Dict[str, Dict[str, str]] = {
    "luna_decomposer": {
        "label": "Luna 원자 셀 분해 (권장)",
        "system_prompt": LUNA_SYSTEM_PROMPT,
        "user_prompt_template": LUNA_USER_TEMPLATE,
    },
    "rdb_financial": {
        "label": "RDB 구조화 헤더 매처",
        "system_prompt": RDB_FINANCIAL_SYSTEM_PROMPT,
        "user_prompt_template": LUNA_USER_TEMPLATE,
    },
    "simple_decomposer": {
        "label": "단순 키워드 원자 분해",
        "system_prompt": SIMPLE_SYSTEM_PROMPT,
        "user_prompt_template": LUNA_USER_TEMPLATE,
    },
}


def decomposer_config_presets() -> List[Dict[str, Any]]:
    return [
        {
            "id": preset_id,
            "label": preset["label"],
            "values": {
                "preset": preset_id,
                "system_prompt": preset["system_prompt"],
                "user_prompt_template": preset["user_prompt_template"],
            },
        }
        for preset_id, preset in DECOMPOSER_PRESETS.items()
    ]
