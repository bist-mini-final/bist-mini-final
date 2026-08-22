"""자연어 복합 질문을 원자 단위 셀 검색 서브쿼리들로 분해하는 LLM 모듈.

사용자의 복합 질문(기간 비교, 다중 재무제표 항목, 복수 기업 등)을 분석하여
벡터 데이터베이스의 단일 셀 임베딩 검색 포맷(`Company: ... | Sheet: ... | Row Header: ... | Column Header: ... | Cell Value: ...`)에
정확히 부합하는 원자적 서브쿼리(Subquery) 목록으로 분해합니다.

Example:
    Input DTO (입력 예시):
    ```json
    {
      "query_context": {
        "question_id": "q-001",
        "question_text": "삼성전자 2023년과 2022년 영업이익을 비교해줘"
      },
      "semantic_match": {
        "matched": true,
        "company_name": "삼성전자",
        "sheets": ["손익계산서"]
      }
    }
    ```

    Output DTO (출력 예시):
    ```json
    {
      "query_context": {
        "question_id": "q-001",
        "question_text": "삼성전자 2023년과 2022년 영업이익을 비교해줘"
      },
      "subqueries": [
        "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: ?",
        "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2022 | Cell Value: ?"
      ]
    }
    ```
"""

from __future__ import annotations

# ==============================================================================
# 1. Imports & Logger Setup
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
    """단일 셀 검색을 위한 원자적 서브쿼리 구조체."""

    company: str = Field(default=UNKNOWN_FIELD, description="대상 기업명 (알 수 없는 경우 '?')")
    sheet: str = Field(default=UNKNOWN_FIELD, description="시트명 (알 수 없는 경우 '?')")
    row_header: str = Field(default=UNKNOWN_FIELD, description="재무 항목 또는 행 헤더")
    column_header: str = Field(default=UNKNOWN_FIELD, description="회계 기간 또는 열 헤더")
    cell_value: str = Field(default=UNKNOWN_FIELD, description="셀 값 제약 조건 또는 '?'")

    def to_serialized_query(self) -> str:
        """벡터 검색에 사용되는 표준 직렬화 문자열로 변환합니다."""
        parts = [f"Company: {self.company or UNKNOWN_FIELD}"]
        parts.append(f"Sheet: {self.sheet or UNKNOWN_FIELD}")
        parts.append(f"Row Header: {self.row_header or UNKNOWN_FIELD}")
        parts.append(f"Column Header: {self.column_header or UNKNOWN_FIELD}")
        parts.append(f"Cell Value: {self.cell_value or UNKNOWN_FIELD}")
        return " | ".join(parts)


class DecomposedSubqueriesResponse(BaseModel):
    """LLM Structured Output 응답 파싱 스키마."""

    items: List[SubqueryItem] = Field(
        default_factory=list,
        description="질문에서 분해된 원자적 셀 서브쿼리 목록",
    )


class DecomposerInputDTO(ModuleInputDTO):
    """Decomposer 모듈 입력 DTO 계약."""

    query_context: QueryContextDTO = Field(description="사용자 질문 컨텍스트")
    semantic_match: Optional[Union[SemanticQueryMatchOutput, LlmQueryRouterOutputDTO, Any]] = Field(
        default=None,
        description="시맨틱 라우터 또는 LLM 라우터의 엔티티/인텐트 스코프 매칭 결과 (선택)",
    )


class DecomposerConfigDTO(ModuleConfigDTO):
    """Decomposer 모듈 설정 DTO 계약."""

    model: str = Field(default=DEFAULT_LLM_MODEL, description="서브쿼리 분해에 사용할 LLM 모델 ID")
    system_prompt: Optional[str] = Field(default=None, description="사용자 지정 시스템 프롬프트")
    user_prompt_template: Optional[str] = Field(default=None, description="사용자 지정 유저 프롬프트 템플릿")


class SubqueriesDTO(ModuleDTO):
    """Decomposer 모듈 출력 DTO 계약."""

    query_context: QueryContextDTO = Field(description="전달받은 질문 컨텍스트")
    subqueries: List[str] = Field(description="직렬화된 단일 셀 검색 서브쿼리 문자열 목록")


# Backward compatibility aliases
DecomposerOutputDTO = SubqueriesDTO
DecomposerOutput = SubqueriesDTO


# ==============================================================================
# 4. Module Implementation
# ==============================================================================
class DecomposerModule(BaseLLMModule):
    """LLM 기반 자연어 질의 원자적 서브쿼리 분해 모듈.

    사용자의 복합 질문을 분석하여 검색 및 수식 계산이 가능한 단일 목적의 원자적 서브쿼리(Subquery) 목록으로 분해합니다.

    Input:
        - `query_context` (`QueryContextDTO`): 원본 사용자 질문 메타데이터 및 텍스트
        - `semantic_match` (`Optional[Any]`): 라우터에서 추출된 대상 기업 및 시트 정보

    Output:
        - `query_context` (`QueryContextDTO`): 원본 사용자 질문 컨텍스트 전달
        - `subqueries` (`List[str]`): 분해된 직렬화 셀 서브쿼리 문자열 리스트
    """

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
        match: Any = (
            match_raw.semantic_match
            if hasattr(match_raw, "semantic_match")
            else match_raw
        )

        # Append entity / scope constraints if provided
        entity_scope_prompt = ""
        scopes = match.company_scopes if (match and hasattr(match, "company_scopes") and match.company_scopes) else []
        if scopes:
            scope_lines = [
                f"- Company: '{sc.canonical_name if hasattr(sc, 'canonical_name') else sc.get('canonical_name')}' | Assigned Topics: [{', '.join(sc.target_topics if hasattr(sc, 'target_topics') else sc.get('target_topics', []))}]"
                for sc in scopes
            ]
            entity_scope_prompt = "\n\n[Entity & Company Intent Scope Assignment]:\n" + "\n".join(scope_lines)
        elif match and getattr(match, "company_name", None):
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
