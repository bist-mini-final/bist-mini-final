"""자연어 질문에서 탐색해야 할 모든 대상 기업, 질문 토픽, 재무제표 시트 스코프 목록을 추론하는 Multi-scope LLM 라우터 모듈.

정적 사전에 의존하지 않고 최신 LLM의 구조화 추론을 활용하여 질문 내 언급된 복수 기업(엔티티)과
관련 재무제표 카테고리(BS, IS, CF 등), 추천 시트 목록(`items`)을 포괄적으로 식별하여 결정론적으로 추출합니다.

Example:
    Input DTO (입력 예시 - 다중 기업 및 다중 시트 비교 질의):
    ```json
    {
      "query_context": {
        "question_id": "q-001",
        "question_text": "삼성전자 2023년 영업이익과 현대자동차 2022년 부채상태를 비교해줘"
      }
    }
    ```

    Output DTO (출력 예시):
    ```json
    {
      "semantic_match": {
        "matched": true,
        "confidence": 0.95,
        "items": [
          {
            "company_name": "삼성전자",
            "raw_mention": "삼성전자",
            "sheets": ["손익계산서"],
            "target_topics": ["영업이익"],
            "matched_score": 1.0
          },
          {
            "company_name": "현대자동차",
            "raw_mention": "현대자동차",
            "sheets": ["재무상태표"],
            "target_topics": ["부채상태", "부채총계"],
            "matched_score": 1.0
          }
        ],
        "sheets": ["손익계산서", "재무상태표"],
        "company_name": "삼성전자",
        "metrics": {
          "kind": "llm_structured",
          "model": "gpt-5.6-luna",
          "latency_seconds": 0.32,
          "estimated_cost_usd": 0.00012
        }
      }
    }
    ```
"""

from __future__ import annotations

# ==============================================================================
# 1. Imports & Logger Setup
# ==============================================================================
import logging
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
from modules.common.config import DEFAULT_ROUTER_MODEL

logger = logging.getLogger(__name__)


# ==============================================================================
# 2. Prompts & Presets
# ==============================================================================
ROUTER_SYSTEM_PROMPT = """You are an expert spreadsheet query router for financial statements and corporate business data.
Analyze the user's natural language question and extract ALL required data scopes (combinations of Company, Financial Sheet Categories, and Specific Financial Topics) into the 'items' list.

CRITICAL GUIDELINES:
1. Multi-Entity & Multi-Sheet Support (CRITICAL):
   - A single question may ask about multiple companies (e.g. '삼성전자' AND '현대자동차') or multiple financial statements (e.g. '영업이익' in IS AND '부채' in BS).
   - ALWAYS extract each distinct (Company + Sheets + Topics) target as an individual item in 'items'.
   - Example 1: "삼성전자 2023년 영업이익과 현대자동차 2022년 부채상태 비교"
     -> Item 1: company_name='삼성전자', sheets=['손익계산서'], target_topics=['영업이익']
     -> Item 2: company_name='현대자동차', sheets=['재무상태표'], target_topics=['부채상태', '부채총계']
   - Example 2: "삼성전자 매출액이랑 부채비율 알려줘"
     -> Item 1: company_name='삼성전자', sheets=['손익계산서'], target_topics=['매출액']
     -> Item 2: company_name='삼성전자', sheets=['재무상태표'], target_topics=['부채비율', '부채총계']

2. Canonical Company Normalization:
   - Normalize colloquial names (e.g. '삼전' -> '삼성전자', '하닉' -> 'SK하이닉스', '현차' -> '현대자동차').

3. Candidate Sheet Names Mapping:
   - Map financial topics to standard sheet names:
     * '매출액', '영업이익', '당기순이익', '매출원가' -> ['손익계산서', '포괄손익계산서']
     * '자산', '부채', '자본', '유동자산', '부채비율' -> ['재무상태표']
     * '영업활동현금흐름', '투자활동현금흐름' -> ['현금흐름표']
     * '배당금', '이익잉여금' -> ['자본변동표', '이익잉여금처분계산서']

4. Confidence:
   - Provide overall confidence score (0.0 to 1.0) of your routing decision."""


# ==============================================================================
# 3. DTOs & Schema Definitions
# ==============================================================================
class CompanyScopeItemDTO(ModuleDTO):
    """질문에서 추출된 기업 엔티티 및 세부 지표/시트 스코프 DTO."""

    company_name: str = Field(description="정규화된 공식 기업명 (예: '삼성전자', '현대자동차')")
    raw_mention: Optional[str] = Field(default=None, description="질문 내 원본 기업 언급 (예: '삼전', '현차')")
    sheets: List[str] = Field(default_factory=list, description="매핑 추천 시트 목록 (예: ['손익계산서'], ['재무상태표'])")
    target_topics: List[str] = Field(default_factory=list, description="추출된 질문 지표/토픽 (예: ['영업이익', '매출액'])")
    matched_score: float = Field(default=1.0, ge=0.0, le=1.0, description="엔티티 매칭 점수 (0.0 ~ 1.0)")
    reason: Optional[str] = Field(default=None, description="선택적 스코프 판단 근거")

    # Backward compatibility aliases
    canonical_name: Optional[str] = None
    suggested_sheets: Optional[List[str]] = None

    def model_post_init(self, __context: Any) -> None:
        if not self.canonical_name:
            self.canonical_name = self.company_name
        if not self.suggested_sheets:
            self.suggested_sheets = self.sheets


class LlmRouterResponse(BaseModel):
    """LLM Structured Output 응답 파싱 스키마."""

    items: List[CompanyScopeItemDTO] = Field(
        default_factory=list,
        description="질문에서 식별된 모든 기업별/시트별 데이터 스코프 목록",
    )
    confidence: float = Field(default=0.85, ge=0.0, le=1.0, description="전체 라우팅 신뢰도 (0.0 ~ 1.0)")
    reason: Optional[str] = Field(default=None, description="선택적 라우팅 판단 근거")


class RouterDecisionDTO(ModuleDTO):
    """자급자족형 구조화 라우팅 결과 DTO."""

    matched: bool = Field(description="유효한 라우팅 대상 매칭 여부")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="라우팅 신뢰도")
    items: List[CompanyScopeItemDTO] = Field(default_factory=list, description="식별된 모든 기업/시트/토픽 데이터 스코프 목록")
    reason: Optional[str] = Field(default=None, description="라우팅 판단 근거")
    sheets: List[str] = Field(default_factory=list, description="전체 스코프 대상 시트 합집합")
    company_name: Optional[str] = Field(default=None, description="단일/주요 대상 기업명")
    company_scopes: List[CompanyScopeItemDTO] = Field(default_factory=list, description="items와 동일한 기업 스코프 목록 (호환용)")
    target: Optional[str] = Field(default=None, description="주요 대상 카테고리 (호환용)")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="실행 메트릭 및 토큰/비용 텔레메트리")


class LlmQueryRouterInputDTO(ModuleInputDTO):
    """LLM Query Router 입력 DTO 계약."""

    query_context: QueryContextDTO = Field(description="사용자 질문 컨텍스트")


class LlmQueryRouterConfigDTO(ModuleConfigDTO):
    """LLM Query Router 설정 DTO 계약."""

    model: str = Field(default=DEFAULT_ROUTER_MODEL, description="질의 라우팅에 사용할 LLM 모델 ID")


class LlmQueryRouterOutputDTO(ModuleDTO):
    """LLM Query Router 출력 DTO 계약."""

    semantic_match: RouterDecisionDTO = Field(description="정형화된 시맨틱 매치 및 멀티 스코프 결과")


# ==============================================================================
# 4. Module Implementation
# ==============================================================================
class LlmQueryRouterModule(BaseLLMModule):
    """LLM 기반 자연어 질의 인텐트 및 대상 시트/기업 멀티 스코프 라우터 모듈.

    사용자 질문을 분석하여 복수 기업 및 재무제표 카테고리(BS, IS, CF 등)의 탐색 대상 스코프 목록(`items`)을 추론합니다.

    Input:
        - `query_context` (`QueryContextDTO`): 원본 사용자 질문 메타데이터 및 텍스트

    Output:
        - `semantic_match` (`RouterDecisionDTO`): 추론된 모든 데이터 스코프 목록(`items`), 추천 시트, 신뢰도
    """

    definition = ModuleDefinition(
        type="llm_query_router",
        label="LLM Query Router",
        category="Logic",
        description="LLM을 활용하여 질문에서 대상 기업 및 관련 시트 카테고리 스코프 목록을 추론하고 라우팅합니다.",
        inputs=["query_context"],
        outputs=["semantic_match"],
        config_fields=["model"],
        version="5",
    )
    input_model = LlmQueryRouterInputDTO
    config_model = LlmQueryRouterConfigDTO
    output_model = LlmQueryRouterOutputDTO

    def __init__(self, completion_client: Optional[Any] = None) -> None:
        super().__init__(completion_client=completion_client)

    def execute(
        self,
        input_data: LlmQueryRouterInputDTO,
        config: Optional[LlmQueryRouterConfigDTO] = None,
    ) -> Dict[str, Any]:
        cfg = config or LlmQueryRouterConfigDTO()
        question = input_data.query_context.question_text

        parsed_res, usage, cost_usd, latency_sec = self.complete_structured(
            messages_or_prompt=f"User Query: {question}",
            response_model=LlmRouterResponse,
            model=cfg.model,
            system_prompt=ROUTER_SYSTEM_PROMPT,
        )

        items = parsed_res.items or []
        matched = bool(items)
        
        # Collect all aggregated sheets and primary company
        all_sheets = list(dict.fromkeys(
            sheet for item in items for sheet in (item.sheets or item.suggested_sheets or [])
        ))
        primary_company = items[0].company_name if items else None
        primary_target = (items[0].sheets[0] if (items and items[0].sheets) else None)

        scopes_dump = [scope.model_dump(mode="json") for scope in items]

        return {
            "semantic_match": {
                "matched": matched,
                "confidence": round(parsed_res.confidence, 4),
                "items": scopes_dump,
                "reason": parsed_res.reason,
                "sheets": all_sheets,
                "company_name": primary_company,
                "company_scopes": scopes_dump,
                "target": primary_target,
                "metrics": {
                    "kind": "llm_structured",
                    "model": cfg.model,
                    "latency_seconds": round(latency_sec, 3),
                    "api_usage": usage or {},
                    "estimated_cost_usd": round(cost_usd, 8),
                },
            }
        }


# Backward compatibility aliases
LlmQueryRouterInput = LlmQueryRouterInputDTO
LlmQueryRouterConfig = LlmQueryRouterConfigDTO
LlmQueryRouterOutput = LlmQueryRouterOutputDTO
LlmQueryRouterExecution = LlmQueryRouterInputDTO

__all__ = [
    "CompanyScopeItemDTO",
    "LlmQueryRouterConfig",
    "LlmQueryRouterConfigDTO",
    "LlmQueryRouterExecution",
    "LlmQueryRouterInput",
    "LlmQueryRouterInputDTO",
    "LlmQueryRouterOutput",
    "LlmQueryRouterOutputDTO",
    "LlmQueryRouterModule",
    "LlmRouterResponse",
    "RouterDecisionDTO",
]
