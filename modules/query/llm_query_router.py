"""자연어 질문에서 대상 기업, 질문 토픽, 재무제표 시트 카테고리를 추론하는 Zero-shot LLM 라우터 모듈.

정적 사전에 의존하지 않고 최신 LLM의 구조화 추론을 활용하여 질문 내 언급된 대상 기업(엔티티)과
관련 재무제표 카테고리(BS, IS, CF 등), 추천 시트 목록을 결정론적으로 추출합니다.

Example:
    Input DTO (입력 예시):
    ```json
    {
      "query_context": {
        "question_id": "q-001",
        "question_text": "삼성전자 작년 매출액이랑 영업이익 얼마야?"
      }
    }
    ```

    Output DTO (출력 예시):
    ```json
    {
      "semantic_match": {
        "matched": true,
        "target": "손익계산서",
        "confidence": 0.95,
        "sheets": ["손익계산서", "포괄손익계산서"],
        "company_name": "삼성전자",
        "company_scopes": [
          {
            "raw_mention": "삼성전자",
            "canonical_name": "삼성전자",
            "matched_score": 1.0,
            "target_topics": ["매출액", "영업이익"],
            "suggested_sheets": ["손익계산서"]
          }
        ],
        "reason": "삼성전자 손익계산서 항목(매출액, 영업이익) 조회 질의",
        "matches": [],
        "query_type": null,
        "subqueries": [],
        "metrics": {
          "kind": "llm_structured",
          "model": "gpt-4o-mini",
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
Analyze the user's natural language question and extract:
1. Target corporate entities mentioned (e.g., '삼성전자', 'SK하이닉스', 'LG에너지솔루션', '카카오').
2. Relevant financial statement categories (e.g., '재무상태표'/'BS', '손익계산서'/'IS', '현금흐름표'/'CF', '자본변동표', '주석'/'Notes').
3. Candidate sheet names relevant to the question metrics.
4. Confidence score (0.0 to 1.0) and concise reason for your routing decision.

Always extract normalized canonical company names and specific financial topics."""


# ==============================================================================
# 3. DTOs & Schema Definitions
# ==============================================================================
class CompanyScopeItemDTO(ModuleDTO):
    """질문에서 추출된 기업 엔티티 및 세부 지표 스코프 DTO."""

    raw_mention: Optional[str] = Field(default=None, description="질문 내 원본 기업 언급 (예: '삼전', '하닉')")
    canonical_name: str = Field(description="정규화된 공식 기업명 (예: '삼성전자', 'SK하이닉스')")
    matched_score: float = Field(default=1.0, ge=0.0, le=1.0, description="엔티티 매칭 점수 (0.0 ~ 1.0)")
    target_topics: List[str] = Field(default_factory=list, description="추출된 질문 지표/토픽 (예: '영업이익', '매출액')")
    suggested_sheets: List[str] = Field(default_factory=list, description="매핑 추천 시트 목록")


class LlmRouterResponse(BaseModel):
    """LLM Structured Output 응답 파싱 스키마."""

    target: Optional[str] = Field(default=None, description="재무제표 카테고리 (예: '손익계산서', '재무상태표', '현금흐름표')")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="라우팅 신뢰도 (0.0 ~ 1.0)")
    company_name: Optional[str] = Field(default=None, description="주요 대상 기업명")
    company_scopes: List[CompanyScopeItemDTO] = Field(default_factory=list, description="식별된 기업별 세부 스코프 목록")
    sheets: List[str] = Field(default_factory=list, description="질의 해결에 필요한 대상 시트 목록")
    reason: str = Field(default="LLM based intent routing", description="라우팅 판단 근거")
    query_type: Optional[int] = Field(default=None, description="질의 유형 코드")
    subqueries: List[str] = Field(default_factory=list, description="추출된 세부 서브쿼리 목록")


class RouterDecisionDTO(ModuleDTO):
    """자급자족형 구조화 라우팅 결과 DTO."""

    matched: bool = Field(description="유효한 라우팅 대상 매칭 여부")
    target: Optional[str] = Field(default=None, description="라우팅 대상 카테고리")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="라우팅 신뢰도")
    sheets: List[str] = Field(default_factory=list, description="대상 시트 목록")
    company_name: Optional[str] = Field(default=None, description="단일/대표 대상 기업명")
    company_scopes: List[CompanyScopeItemDTO] = Field(default_factory=list, description="기업별 세부 인텐트 스코프 목록")
    reason: str = Field(description="라우팅 판단 근거")
    matches: List[Dict[str, Any]] = Field(default_factory=list, description="유사도 매치 목록 (LLM 라우터는 빈 리스트)")
    query_type: Optional[int] = Field(default=None, description="질의 유형 코드")
    subqueries: List[str] = Field(default_factory=list, description="서브쿼리 목록")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="실행 메트릭 및 토큰/비용 텔레메트리")


class LlmQueryRouterInputDTO(ModuleInputDTO):
    """LLM Query Router 입력 DTO 계약."""

    query_context: QueryContextDTO = Field(description="사용자 질문 컨텍스트")


class LlmQueryRouterConfigDTO(ModuleConfigDTO):
    """LLM Query Router 설정 DTO 계약."""

    model: str = Field(default=DEFAULT_ROUTER_MODEL, description="질의 라우팅에 사용할 LLM 모델 ID")


class LlmQueryRouterOutputDTO(ModuleDTO):
    """LLM Query Router 출력 DTO 계약."""

    semantic_match: RouterDecisionDTO = Field(description="정형화된 시맨틱 매치 및 스코프 결과")


# ==============================================================================
# 4. Module Implementation
# ==============================================================================
class LlmQueryRouterModule(BaseLLMModule):
    """LLM 기반 자연어 질의 인텐트 및 대상 시트/기업 라우터 모듈.

    사용자 질문을 분석하여 대상 기업과 재무제표 카테고리(BS, IS, CF 등) 및 시트 후보를 추론합니다.

    Input:
        - `query_context` (`QueryContextDTO`): 원본 사용자 질문 메타데이터 및 텍스트

    Output:
        - `semantic_match` (`RouterDecisionDTO`): 추론된 대상 기업, 재무 카테고리, 추천 시트 목록 및 신뢰도
    """

    definition = ModuleDefinition(
        type="llm_query_router",
        label="LLM Query Router",
        category="Logic",
        description="LLM을 활용하여 질문에서 대상 기업 및 관련 시트 카테고리를 추론하고 라우팅합니다.",
        inputs=["query_context"],
        outputs=["semantic_match"],
        config_fields=["model"],
        version="4",
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

        matched = parsed_res.target is not None or bool(parsed_res.sheets) or bool(parsed_res.company_name)

        return {
            "semantic_match": {
                "matched": matched,
                "target": parsed_res.target,
                "confidence": round(parsed_res.confidence, 4),
                "sheets": parsed_res.sheets,
                "company_name": parsed_res.company_name,
                "company_scopes": [scope.model_dump(mode="json") for scope in parsed_res.company_scopes],
                "reason": parsed_res.reason,
                "matches": [],
                "query_type": parsed_res.query_type,
                "subqueries": parsed_res.subqueries,
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
