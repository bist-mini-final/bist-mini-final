"""자연어 복합 질문을 LLM 라우터 스코프 기반의 원자 단위 셀 검색 서브쿼리들로 분해하는 LLM 모듈.

사용자의 복합 질문(기간 비교, 다중 재무제표 항목, 복수 기업 등)과 LLM 쿼리 라우터(`LlmQueryRouterModule`)의 엔티티/시트 분석 결과를 결합하여
벡터 데이터베이스의 단일 셀 임베딩 검색 포맷(`Company: ... | Sheet: ... | Row Header: ... | Column Header: ... | Cell Value: ...`)에
정확히 부합하는 원자적 서브쿼리(Subquery) 목록으로 분해합니다.

Example:
    Input DTO (입력 예시 - LLM Query Router 다중 스코프 연계):
    ```json
    {
      "query_context": {
        "question_id": "q-001",
        "question_text": "삼성전자 2023년 영업이익과 현대자동차 2022년 부채상태를 비교해줘"
      },
      "semantic_match": {
        "matched": true,
        "confidence": 0.95,
        "items": [
          {
            "company_name": "삼성전자",
            "sheets": ["손익계산서"],
            "target_topics": ["영업이익"]
          },
          {
            "company_name": "현대자동차",
            "sheets": ["재무상태표"],
            "target_topics": ["부채상태", "부채총계"]
          }
        ],
        "reason": "삼성전자 손익계산서 및 현대자동차 재무상태표 복합 비교 질의"
      }
    }
    ```

    Output DTO (출력 예시):
    ```json
    {
      "query_context": {
        "question_id": "q-001",
        "question_text": "삼성전자 2023년 영업이익과 현대자동차 2022년 부채상태를 비교해줘"
      },
      "items": [
        {
          "company": "삼성전자",
          "sheet": "손익계산서",
          "row_header": "영업이익",
          "column_header": "2023",
          "cell_value": "?",
          "text": "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: ?"
        },
        {
          "company": "현대자동차",
          "sheet": "재무상태표",
          "row_header": "부채총계",
          "column_header": "2022",
          "cell_value": "?",
          "text": "Company: 현대자동차 | Sheet: 재무상태표 | Row Header: 부채총계 | Column Header: 2022 | Cell Value: ?"
        }
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

from pydantic import BaseModel, Field, model_validator

from modules.common.base_llm import (
    BaseLLMModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleDTO,
    ModuleInputDTO,
    QueryContextDTO,
)
from modules.common.config import DEFAULT_LLM_MODEL
from modules.query.llm_query_router import (
    CompanyScopeItemDTO,
    LlmQueryRouterOutputDTO,
    RouterDecisionDTO,
)
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
   - Partition subqueries strictly per company.
5. LLM Router Target Scope Compliance:
   - If [LLM Router Target Scopes] are provided, strictly prioritize the specified Company, Topics, and Suggested Sheets."""

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
    text: Optional[str] = Field(default=None, description="직렬화된 단일 셀 검색 포맷 텍스트")

    def to_serialized_query(self) -> str:
        """벡터 검색에 사용되는 표준 직렬화 문자열로 변환하고 text 필드를 채웁니다."""
        parts = [f"Company: {self.company or UNKNOWN_FIELD}"]
        parts.append(f"Sheet: {self.sheet or UNKNOWN_FIELD}")
        parts.append(f"Row Header: {self.row_header or UNKNOWN_FIELD}")
        parts.append(f"Column Header: {self.column_header or UNKNOWN_FIELD}")
        parts.append(f"Cell Value: {self.cell_value or UNKNOWN_FIELD}")
        serialized = " | ".join(parts)
        self.text = serialized
        return serialized


class DecomposedSubqueriesResponse(BaseModel):
    """LLM Structured Output 응답 파싱 스키마."""

    items: List[SubqueryItem] = Field(
        default_factory=list,
        description="질문에서 분해된 원자적 셀 서브쿼리 목록",
    )


class DecomposerInputDTO(ModuleInputDTO):
    """Decomposer 모듈 입력 DTO 계약."""

    query_context: QueryContextDTO = Field(description="사용자 질문 컨텍스트")
    semantic_match: Optional[Union[RouterDecisionDTO, LlmQueryRouterOutputDTO, SemanticQueryMatchOutput, Dict[str, Any]]] = Field(
        default=None,
        description="LLM 쿼리 라우터(LlmQueryRouterModule)의 엔티티/인텐트/시트 라우팅 결과 (RouterDecisionDTO)",
    )


class DecomposerConfigDTO(ModuleConfigDTO):
    """Decomposer 모듈 설정 DTO 계약."""

    model: str = Field(default=DEFAULT_LLM_MODEL, description="서브쿼리 분해에 사용할 LLM 모델 ID")
    system_prompt: Optional[str] = Field(default=None, description="사용자 지정 시스템 프롬프트")
    user_prompt_template: Optional[str] = Field(default=None, description="사용자 지정 유저 프롬프트 템플릿")


class SubqueriesDTO(ModuleDTO):
    """Decomposer 모듈 출력 DTO 계약."""

    query_context: QueryContextDTO = Field(description="전달받은 질문 컨텍스트")
    items: List[SubqueryItem] = Field(
        default_factory=list,
        description="구조화된 원자적 서브쿼리 객체 목록 (company, sheet, row_header, column_header, cell_value, text)",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_subqueries_input(cls, data: Any) -> Any:
        """subqueries 리스트가 전달될 경우 items 목록으로 자동 변환합니다."""
        if isinstance(data, dict):
            raw_items = data.get("items")
            raw_subqueries = data.get("subqueries")
            if not raw_items and raw_subqueries:
                data["items"] = [
                    SubqueryItem(text=sq) if isinstance(sq, str) else sq
                    for sq in raw_subqueries
                ]
        return data

    @property
    def subqueries(self) -> List[str]:
        """직렬화된 단일 셀 검색 서브쿼리 문자열 목록 (하위 호환 헬퍼 프로퍼티)."""
        return [item.text or item.to_serialized_query() for item in self.items]


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
        - `semantic_match` (`Optional[Union[LlmQueryRouterOutputDTO, Any]]`): LLM 라우터에서 추출된 대상 기업, 인텐트 토픽, 추천 시트 정보

    Output:
        - `query_context` (`QueryContextDTO`): 원본 사용자 질문 컨텍스트 전달
        - `items` (`List[SubqueryItem]`): 기업명, 시트명, 행/열 헤더 및 text를 포함한 구조화 서브쿼리 목록
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
        version="8",
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

        # Resolve routing scopes from LLM Query Router or Semantic Matcher
        match_raw = input_data.semantic_match
        match: Any = (
            match_raw.semantic_match
            if hasattr(match_raw, "semantic_match")
            else match_raw
        )

        # Append entity / scope constraints from LLM Router
        entity_scope_prompt = ""
        if match:
            scope_lines = []
            scopes = getattr(match, "items", None) or getattr(match, "company_scopes", None) or (
                match.get("items") or match.get("company_scopes") if isinstance(match, dict) else []
            )
            if scopes:
                for idx, sc in enumerate(scopes, start=1):
                    cname = getattr(sc, "company_name", None) or getattr(sc, "canonical_name", None) or (
                        sc.get("company_name") or sc.get("canonical_name") if isinstance(sc, dict) else ""
                    )
                    topics = getattr(sc, "target_topics", None) or (
                        sc.get("target_topics") if isinstance(sc, dict) else []
                    )
                    sheets = getattr(sc, "sheets", None) or getattr(sc, "suggested_sheets", None) or (
                        sc.get("sheets") or sc.get("suggested_sheets") if isinstance(sc, dict) else []
                    )
                    topics_str = ", ".join(str(t) for t in topics) if topics else ""
                    sheets_str = ", ".join(str(s) for s in sheets) if sheets else ""
                    scope_lines.append(
                        f"- Scope {idx}: Company='{cname}' | Topics=[{topics_str}] | Target Sheets=[{sheets_str}]"
                    )
                entity_scope_prompt = "\n\n[LLM Router Target Data Scopes]:\n" + "\n".join(scope_lines)
            elif getattr(match, "company_name", None) or (isinstance(match, dict) and match.get("company_name")):
                cname = getattr(match, "company_name", None) or match.get("company_name")
                sheets = getattr(match, "sheets", None) or (
                    match.get("sheets") if isinstance(match, dict) else []
                )
                sheets_list_str = ", ".join(str(s) for s in sheets) if sheets else ""
                entity_scope_prompt = f"\n\n[LLM Router Target Scope]: Target Company: '{cname}', Sheets: [{sheets_list_str}]"

        prompt = user_tmpl.format(question=input_data.query_context.question_text) + entity_scope_prompt

        parsed_resp, _, _, _ = self.complete_structured(
            messages_or_prompt=prompt,
            response_model=DecomposedSubqueriesResponse,
            model=cfg.model,
            system_prompt=sys_prompt,
        )

        items_dict: Dict[str, SubqueryItem] = {}
        for item in parsed_resp.items:
            if not item:
                continue
            serialized = item.to_serialized_query()
            if serialized not in items_dict:
                items_dict[serialized] = item

        items_list = list(items_dict.values())

        return {
            "query_context": input_data.query_context.model_dump(mode="json"),
            "items": [item.model_dump(mode="json") for item in items_list],
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
