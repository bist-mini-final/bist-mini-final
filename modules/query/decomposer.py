import json
import re
from typing import Any, Dict, Iterable, List, Literal, Optional, Sequence, cast

from pydantic import BaseModel, Field

from backend.providers.llm.chat_completion import ChatCompletionClient, ChatCompletionError
from modules.common.base_module import (
    BaseModule,
    ModuleConfigDTO,
    ModuleConfigPreset,
    ModuleDefinition,
    ModuleDTO,
    ModuleExecutionError,
    ModuleInputDTO,
    QueryContextDTO,
)
from modules.common.config import DEFAULT_LLM_MODEL


# ==============================================================================
# Subquery Formatting & Normalization Helpers
# ==============================================================================
UNKNOWN_FIELD = "?"

PERIOD_EQUIVALENT_GROUPS: Sequence[Sequence[str]] = (
    ("LTM", "FY0", "FY2025", "2025-12-31"),
    ("FY-1", "FY2024", "2024-12-31"),
    ("FY-2", "FY2023", "2023-12-31"),
    ("FY-3", "FY2022", "2022-12-31"),
    ("FY-4", "FY2021", "2021-12-31"),
    ("FY1", "FY2026", "2026-12-31"),
)

METRIC_EQUIVALENT_GROUPS: Sequence[Sequence[str]] = (
    (
        "TEV/EBITDA",
        "Enterprise Value/EBITDA",
        "Enterprise Value to EBITDA",
        "Enterprise Value to EBITDA Multiple",
    ),
    ("Total Enterprise Value", "Enterprise Value", "TEV"),
    ("Market Capitalization", "Market Cap", "Equity Market Value"),
    ("Net Income", "Net Income to Company"),
    ("Total Revenue", "Total Revenues", "Revenue", "Revenues", "Net Sales"),
    ("Operating Income", "EBIT", "Operating Profit"),
    ("Capital Expenditure", "CapEx", "Capital Expenditure (actual)"),
    (
        "Shares Outstanding",
        "Weighted Avg. Diluted Shares Out.",
        "Total Shares Out. on Filing Date",
    ),
    (
        "Cash and Short-Term Investments",
        "Total Cash & ST Investments",
        "Cash and Cash Equivalents",
        "Short-Term Investments",
    ),
    ("EBITDA Margin", "Margin %", "EBITDA Margin %"),
)


def serialize_structured_query(
    sheet: str = UNKNOWN_FIELD,
    row_header: str = UNKNOWN_FIELD,
    column_header: str = UNKNOWN_FIELD,
    cell_value: str = UNKNOWN_FIELD,
) -> str:
    return (
        f"Sheet: {sheet or UNKNOWN_FIELD} | "
        f"Row Header: {row_header or UNKNOWN_FIELD} | "
        f"Column Header: {column_header or UNKNOWN_FIELD} | "
        f"Cell Value: {cell_value or UNKNOWN_FIELD}"
    )


def normalize_structured_query(value: object) -> str:
    """Fix the field order and fill every missing field with `?`."""
    if not isinstance(value, str):
        raise ValueError("서브쿼리 항목은 문자열이어야 합니다")
    text = value.strip()
    fields = {}
    for part in text.split("|"):
        if ":" not in part:
            continue
        key, field_value = part.split(":", 1)
        fields[key.strip().lower()] = field_value.strip() or UNKNOWN_FIELD
    if not fields:
        raise ValueError("서브쿼리에 구조화 필드가 없습니다")

    sheet = fields.get("sheet", UNKNOWN_FIELD)
    sheet_aliases = {
        "balance sheet": "Balance_Sheet",
        "balance_sheet": "Balance_Sheet",
        "income statement": "Income_Statement",
        "income_statement": "Income_Statement",
        "cash flow statement": "Cash_Flow",
        "cash flow": "Cash_Flow",
        "cash_flow": "Cash_Flow",
        "key stats": "Key_Stats",
        "key statistics": "Key_Stats",
        "key_stats": "Key_Stats",
    }
    sheet = sheet_aliases.get(sheet.lower(), sheet)
    return serialize_structured_query(
        sheet=sheet,
        row_header=fields.get("row header", UNKNOWN_FIELD),
        column_header=fields.get("column header", UNKNOWN_FIELD),
        cell_value=fields.get("cell value", UNKNOWN_FIELD),
    )


def normalize_subqueries(values: Iterable[object]) -> List[str]:
    normalized: List[str] = []
    for value in values:
        if not str(value).strip():
            continue
        query = normalize_structured_query(value)
        if query not in normalized:
            normalized.append(query)
    return normalized


def _structured_fields(value: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for part in value.split("|"):
        key, separator, field_value = part.partition(":")
        if separator:
            fields[key.strip().lower()] = field_value.strip() or UNKNOWN_FIELD
    return fields


def _alias_pattern(alias: str) -> str:
    return rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])"


def _expand_metric_aliases(row_header: str) -> List[str]:
    variants = [row_header]
    for group in METRIC_EQUIVALENT_GROUPS:
        expanded: List[str] = []
        aliases = sorted(group, key=len, reverse=True)
        for variant in variants:
            matched_alias = next(
                (
                    alias
                    for alias in aliases
                    if re.search(_alias_pattern(alias), variant, flags=re.IGNORECASE)
                ),
                None,
            )
            replacements = group if matched_alias else (variant,)
            for replacement in replacements:
                candidate = (
                    re.sub(
                        _alias_pattern(matched_alias),
                        replacement,
                        variant,
                        count=1,
                        flags=re.IGNORECASE,
                    )
                    if matched_alias
                    else replacement
                )
                if candidate not in expanded:
                    expanded.append(candidate)
        variants = expanded
    return variants


def _expand_period_aliases(column_header: str) -> List[str]:
    normalized = column_header.strip()
    for group in PERIOD_EQUIVALENT_GROUPS:
        if any(normalized.casefold() == alias.casefold() for alias in group):
            return list(group)
    return [normalized]


def augment_subqueries(subqueries: Iterable[str]) -> List[str]:
    """Expand each atomic query into every known metric and period alias pair."""
    result: List[str] = []

    def append(query: str) -> None:
        normalized = normalize_structured_query(query)
        if normalized not in result:
            result.append(normalized)

    for subquery in subqueries:
        normalized = normalize_structured_query(subquery)
        fields = _structured_fields(normalized)
        row_header = re.sub(
            r"\b(Actual|Estimate|Forecast)\b",
            "",
            fields.get("row header", UNKNOWN_FIELD),
            flags=re.IGNORECASE,
        )
        row_header = re.sub(r"\s{2,}", " ", row_header).strip() or UNKNOWN_FIELD
        column_header = fields.get("column header", UNKNOWN_FIELD)

        for metric_variant in _expand_metric_aliases(row_header):
            for period_variant in _expand_period_aliases(column_header):
                append(
                    serialize_structured_query(
                        sheet=fields.get("sheet", UNKNOWN_FIELD),
                        row_header=metric_variant,
                        column_header=period_variant,
                        cell_value=fields.get("cell value", UNKNOWN_FIELD),
                    )
                )
    return result


# ==============================================================================
# Prompts & Presets
# ==============================================================================
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


# ==============================================================================
# DTOs
# ==============================================================================
class DecomposerInputDTO(ModuleInputDTO):
    query_context: QueryContextDTO = Field(
        description="Query Input에서 전달된 질문 ID와 원문 질문",
    )


class DecomposerConfigDTO(ModuleConfigDTO):
    model: str = Field(
        default=DEFAULT_LLM_MODEL, description="질의 분해에 사용할 LLM ID"
    )
    preset: Literal[
        "luna_decomposer",
        "rdb_financial",
        "simple_decomposer",
    ] = Field(
        default="luna_decomposer",
        description="적용할 프롬프트 프리셋 ID",
    )
    system_prompt: str = Field(
        default=LUNA_SYSTEM_PROMPT,
        description="원자 단위 서브쿼리 생성 규칙을 정의하는 시스템 프롬프트",
    )
    user_prompt_template: str = Field(
        default=LUNA_USER_TEMPLATE,
        description="{question} 변수를 지원하는 사용자 프롬프트 템플릿",
    )


class DecomposerExecutionDTO(DecomposerInputDTO, DecomposerConfigDTO):
    """Internal union of the public input and module settings."""


class SubqueriesDTO(ModuleDTO):
    query_context: QueryContextDTO = Field(
        description="분해 대상이 된 원본 질문 메타데이터"
    )
    subqueries: List[str] = Field(
        description="구조화된 4필드 포맷의 서브쿼리 목록",
    )


# ==============================================================================
# Module Implementation
# ==============================================================================
class DecomposerModule(BaseModule):
    definition = ModuleDefinition(
        type="decomposer",
        label="LLM Query Decomposer",
        category="Logic",
        description="사용자 질문을 원자 단위 서브쿼리로 분해합니다.",
        inputs=["input"],
        outputs=["output"],
        config_fields=["model", "preset", "system_prompt", "user_prompt_template"],
        raw_output=True,
        version="6",
    )
    input_model = DecomposerInputDTO
    config_model = DecomposerConfigDTO
    execution_model = DecomposerExecutionDTO
    output_model = SubqueriesDTO

    def __init__(
        self,
        completion_client: Optional[ChatCompletionClient] = None,
    ) -> None:
        self.completion_client = completion_client or ChatCompletionClient()

    def execute(
        self,
        input_data: DecomposerInputDTO,
        config: Optional[DecomposerConfigDTO] = None,
    ) -> Dict[str, Any]:
        if config is None and isinstance(input_data, DecomposerExecutionDTO):
            config = input_data
        model_name = config.model if config else DEFAULT_LLM_MODEL
        sys_prompt = config.system_prompt if config else LUNA_SYSTEM_PROMPT
        user_tmpl = config.user_prompt_template if config else LUNA_USER_TEMPLATE

        prompt = user_tmpl.format(
            question=input_data.query_context.question_text,
        )
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": prompt},
        ]
        if hasattr(self.completion_client, "complete_with_metadata"):
            try:
                res = self.completion_client.complete_with_metadata(
                    model=model_name,
                    messages=messages,
                )
                text = res.content
                self.last_usage = res.usage
            except Exception:
                text = self.completion_client.complete(model_name, messages)
        else:
            text = self.completion_client.complete(model_name, messages)
        self.last_model = model_name
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as error:
            raise ModuleExecutionError(
                f"LLM 출력을 JSON으로 파싱할 수 없습니다: {text}"
            ) from error
        if not isinstance(parsed, list):
            raise ModuleExecutionError("LLM 출력은 JSON 배열이어야 합니다")
        try:
            normalized = normalize_subqueries(parsed)
        except ValueError as error:
            raise ModuleExecutionError(str(error)) from error
        return {
            "query_context": input_data.query_context.model_dump(mode="json"),
            "subqueries": augment_subqueries(normalized),
        }
