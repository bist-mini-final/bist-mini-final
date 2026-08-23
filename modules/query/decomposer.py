"""Decompose a natural-language question into atomic spreadsheet subqueries."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from modules.common.base_llm import (
    BaseLLMModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleDTO,
    ModuleInputDTO,
    QueryContextDTO,
)
from modules.common.config import DEFAULT_LLM_MODEL

LUNA_SYSTEM_PROMPT = """You are a Spreadsheet Query Decomposition Assistant.
Decompose the user's question into every atomic cell-search subquery required to
answer it. Each stored vector represents one spreadsheet cell.

Rules:
1. Create separate subqueries for each company, metric, and period.
2. Normalize row headers and include useful canonical synonyms when needed.
3. Normalize periods such as YYYY, FYYYYY, quarter, LTM, and TTM.
4. Preserve the company and likely sheet on every subquery.
5. Use '?' only when a field truly cannot be inferred.
"""

LUNA_USER_TEMPLATE = 'User Query: "{question}"'
UNKNOWN_FIELD = "?"


class SubqueryItem(ModuleDTO):
    """One atomic spreadsheet-cell search intent."""

    company: str = Field(default=UNKNOWN_FIELD)
    sheet: str = Field(default=UNKNOWN_FIELD)
    row_header: str = Field(default=UNKNOWN_FIELD)
    column_header: str = Field(default=UNKNOWN_FIELD)
    cell_value: str = Field(default=UNKNOWN_FIELD)
    text: Optional[str] = None

    def to_serialized_query(self) -> str:
        serialized = " | ".join(
            (
                f"Company: {self.company or UNKNOWN_FIELD}",
                f"Sheet: {self.sheet or UNKNOWN_FIELD}",
                f"Row Header: {self.row_header or UNKNOWN_FIELD}",
                f"Column Header: {self.column_header or UNKNOWN_FIELD}",
                f"Cell Value: {self.cell_value or UNKNOWN_FIELD}",
            )
        )
        self.text = serialized
        return serialized


class DecomposedSubqueriesResponse(BaseModel):
    items: List[SubqueryItem] = Field(default_factory=list)


class DecomposerInputDTO(ModuleInputDTO):
    query_context: QueryContextDTO


class DecomposerConfigDTO(ModuleConfigDTO):
    model: str = Field(default=DEFAULT_LLM_MODEL)
    system_prompt: Optional[str] = None
    user_prompt_template: Optional[str] = None


class SubqueriesDTO(ModuleDTO):
    query_context: QueryContextDTO
    items: List[SubqueryItem] = Field(default_factory=list)


class DecomposerModule(BaseLLMModule):
    """Creates atomic subqueries before any collection is selected."""

    definition = ModuleDefinition(
        type="decomposer",
        label="LLM Query Decomposer",
        category="Logic",
        description=(
            "사용자 질문을 collection과 독립적인 원자 셀 검색 서브쿼리로 분해합니다."
        ),
        inputs=["query_context"],
        outputs=["output"],
        config_fields=["model", "system_prompt", "user_prompt_template"],
        raw_output=True,
        version="9",
    )
    input_model = DecomposerInputDTO
    config_model = DecomposerConfigDTO
    output_model = SubqueriesDTO

    def __init__(self, completion_client: Any) -> None:
        super().__init__(completion_client=completion_client)

    def execute(
        self,
        input_data: DecomposerInputDTO,
        config: Optional[DecomposerConfigDTO] = None,
    ) -> Dict[str, Any]:
        cfg = config or DecomposerConfigDTO()
        parsed, _, _, _ = self.complete_structured(
            messages_or_prompt=(cfg.user_prompt_template or LUNA_USER_TEMPLATE).format(
                question=input_data.query_context.question_text
            ),
            response_model=DecomposedSubqueriesResponse,
            model=cfg.model,
            system_prompt=cfg.system_prompt or LUNA_SYSTEM_PROMPT,
        )
        unique: Dict[str, SubqueryItem] = {}
        for item in parsed.items:
            serialized = item.to_serialized_query()
            unique.setdefault(serialized, item)
        return {
            "query_context": input_data.query_context.model_dump(mode="json"),
            "items": [item.model_dump(mode="json") for item in unique.values()],
        }


__all__ = [
    "DecomposedSubqueriesResponse",
    "DecomposerConfigDTO",
    "DecomposerInputDTO",
    "DecomposerModule",
    "SubqueriesDTO",
    "SubqueryItem",
]
