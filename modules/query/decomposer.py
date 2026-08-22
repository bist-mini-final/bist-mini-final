from __future__ import annotations

# ==============================================================================
# 1. Imports
# ==============================================================================
import logging
from typing import Any, Dict, List, Optional, Union

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
from modules.query.llm_query_router import LlmQueryRouterOutputDTO
from modules.query.semantic_query_matcher import SemanticQueryMatchOutput

logger = logging.getLogger(__name__)


# ==============================================================================
# 2. Prompts & Presets
# ==============================================================================
LUNA_SYSTEM_PROMPT = """You are a Spreadsheet Query Decomposition Assistant for RAG retrieval over structured Excel workbooks.
Analyze the user's natural language question and decompose it into all necessary atomic cell-search subqueries.
Retrieval coverage and accuracy are prioritized over brevity.

Guidelines:
1. Header Concept Normalization & Synonym Generation:
   - Normalize question concepts into formal spreadsheet header terms (row headers and column headers).
   - Generate separate subqueries for canonical names, common synonyms, English equivalents, and domain abbreviations.
2. Period Variant Handling:
   - Generate all corresponding period variants (e.g. YYYY, FYYYYY, quarters, LTM, TTM).
3. Atomic Single-Cell Subquery Principle (CRITICAL):
   - In our vector database, EACH VECTOR CORRESPONDS TO A SINGLE ATOMIC CELL.
   - Generate individual atomic subqueries for every single period and metric within that scope.
4. Company and Entity-to-Intent Isolation (CRITICAL):
   - Populate the 'company' field with the canonical company name.
   - Partition subqueries strictly per company."""

LUNA_USER_TEMPLATE = "User Query: \"{question}\""

UNKNOWN_FIELD = "?"


# ==============================================================================
# 3. DTOs & Item Models
# ==============================================================================
class SubqueryItem(BaseModel):
    company: str = Field(default=UNKNOWN_FIELD, description="Target company name, or '?' if unknown")
    sheet: str = Field(default=UNKNOWN_FIELD, description="Sheet name, or '?' if not explicitly known")
    row_header: str = Field(default=UNKNOWN_FIELD, description="Financial metric or row header")
    column_header: str = Field(default=UNKNOWN_FIELD, description="Fiscal period or column header")
    cell_value: str = Field(default=UNKNOWN_FIELD, description="Target cell value constraint or '?'")

    def to_serialized_query(self) -> str:
        """Serialize into canonical vector search string format."""
        parts = [f"Company: {self.company or UNKNOWN_FIELD}"]
        parts.append(f"Sheet: {self.sheet or UNKNOWN_FIELD}")
        parts.append(f"Row Header: {self.row_header or UNKNOWN_FIELD}")
        parts.append(f"Column Header: {self.column_header or UNKNOWN_FIELD}")
        parts.append(f"Cell Value: {self.cell_value or UNKNOWN_FIELD}")
        return " | ".join(parts)


class DecomposedSubqueriesResponse(BaseModel):
    items: List[SubqueryItem] = Field(
        default_factory=list,
        description="List of atomic cell subqueries decomposed from the query",
    )


class DecomposerInputDTO(ModuleInputDTO):
    query_context: QueryContextDTO
    semantic_match: Optional[Union[SemanticQueryMatchOutput, LlmQueryRouterOutputDTO]] = Field(
        default=None,
        description="시맨틱 라우터 또는 LLM 라우터의 엔티티/인텐트 스코프 매칭 결과",
    )


class DecomposerConfigDTO(ModuleConfigDTO):
    model: str = Field(default=DEFAULT_LLM_MODEL, description="서브쿼리 분해에 사용할 LLM 모델 ID")
    system_prompt: Optional[str] = Field(default=None, description="사용자 지정 시스템 프롬프트")
    user_prompt_template: Optional[str] = Field(default=None, description="사용자 지정 유저 프롬프트 템플릿")


class SubqueriesDTO(ModuleDTO):
    query_context: QueryContextDTO
    subqueries: List[str]


# Backward compatibility aliases
DecomposerOutputDTO = SubqueriesDTO
DecomposerOutput = SubqueriesDTO


# ==============================================================================
# 4. Module Implementation
# ==============================================================================
class DecomposerModule(BaseLLMModule):
    """Decomposes complex natural language user queries into atomic cell search subqueries."""

    definition = ModuleDefinition(
        type="decomposer",
        label="LLM Query Decomposer",
        category="Logic",
        description="사용자 질문을 원자 단위 셀 검색 서브쿼리들로 분해합니다.",
        inputs=["input"],
        outputs=["output"],
        config_fields=["model", "system_prompt", "user_prompt_template"],
        raw_output=True,
        version="7",
    )
    input_model = DecomposerInputDTO
    config_model = DecomposerConfigDTO
    output_model = SubqueriesDTO

    def execute(
        self,
        input_data: DecomposerInputDTO,
        config: Optional[DecomposerConfigDTO] = None,
    ) -> Dict[str, Any]:
        cfg = config or DecomposerConfigDTO()
        sys_prompt = cfg.system_prompt or LUNA_SYSTEM_PROMPT
        user_tmpl = cfg.user_prompt_template or LUNA_USER_TEMPLATE

        # Resolve semantic scopes if available (from Semantic Matcher or LLM Router)
        match_raw = input_data.semantic_match
        match: Optional[SemanticQueryMatchOutput] = (
            match_raw.semantic_match
            if isinstance(match_raw, LlmQueryRouterOutputDTO)
            else match_raw
        )

        # Append entity / scope constraints if provided
        entity_scope_prompt = ""
        scopes = match.company_scopes if (match and match.company_scopes) else []
        if scopes:
            scope_lines = [
                f"- Company: '{sc.canonical_name}' | Assigned Topics: [{', '.join(sc.target_topics) if sc.target_topics else 'All'}]"
                for sc in scopes
            ]
            entity_scope_prompt = "\n\n[Entity & Company Intent Scope Assignment]:\n" + "\n".join(scope_lines)
        elif match and match.company_name:
            entity_scope_prompt = f"\n\n[Entity Assignment]: Target Company: '{match.company_name}'"

        prompt = user_tmpl.format(question=input_data.query_context.question_text) + entity_scope_prompt

        parsed_resp, _, _, _ = self.complete_structured(
            messages_or_prompt=prompt,
            response_model=DecomposedSubqueriesResponse,
            model=cfg.model,
            system_prompt=sys_prompt,
        )

        subqueries = list(dict.fromkeys(item.to_serialized_query() for item in parsed_resp.items if item))
        return {
            "query_context": input_data.query_context.model_dump(mode="json"),
            "subqueries": subqueries,
        }


# ==============================================================================
# 5. Exports
# ==============================================================================
__all__ = [
    "LUNA_SYSTEM_PROMPT",
    "LUNA_USER_TEMPLATE",
    "UNKNOWN_FIELD",
    "DecomposedSubqueriesResponse",
    "DecomposerConfigDTO",
    "DecomposerInputDTO",
    "DecomposerModule",
    "SubqueriesDTO",
    "SubqueryItem",
]
