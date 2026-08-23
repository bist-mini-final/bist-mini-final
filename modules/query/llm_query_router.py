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
        "items": [
          {
            "company_name": "삼성전자",
            "sheets": ["손익계산서"]
          },
          {
            "company_name": "현대자동차",
            "sheets": ["재무상태표"]
          }
        ],
        "metrics": {
          "kind": "llm_structured",
          "model": "gpt-5.6-luna",
          "latency_seconds": 0.21,
          "estimated_cost_usd": 0.00008
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
ROUTER_SYSTEM_PROMPT = """You are an expert financial spreadsheet query router.
Analyze the user's natural language question and identify all required target data scopes (combinations of canonical Company Name and standard Financial Statement Sheet Categories) into the 'items' list.

CRITICAL GUIDELINES:
1. Multi-Entity & Multi-Sheet Support:
   - A single question may ask about multiple companies or multiple financial statements.
   - ALWAYS extract each distinct (Company Name + Target Sheets) as an individual item in 'items'.

2. Company & Sheet Normalization:
   - Identify the formal canonical corporate entity name (e.g. '삼성전자', '현대자동차', 'SK하이닉스').
   - Infer the relevant standard financial statement sheet names (e.g., '손익계산서', '재무상태표', '현금흐름표', '자본변동표')."""


# ==============================================================================
# 3. DTOs & Schema Definitions
# ==============================================================================
class CompanyScopeItemDTO(ModuleDTO):
    """질문에서 추출된 대상 기업 및 추천 재무제표 시트 스코프 DTO."""

    company_name: str = Field(description="정규화된 공식 기업명 (예: '삼성전자', '현대자동차')")
    sheets: List[str] = Field(default_factory=list, description="매핑 추천 시트 목록 (예: ['손익계산서'], ['재무상태표'])")
    reason: Optional[str] = Field(default=None, description="선택적 스코프 판단 근거")


class LlmRouterResponse(BaseModel):
    """LLM Structured Output 응답 파싱 스키마."""

    items: List[CompanyScopeItemDTO] = Field(
        default_factory=list,
        description="질문에서 식별된 모든 기업별/시트별 데이터 스코프 목록",
    )


class RouterDecisionDTO(ModuleDTO):
    """자급자족형 구조화 라우팅 결과 DTO."""

    items: List[CompanyScopeItemDTO] = Field(default_factory=list, description="식별된 모든 기업/시트/토픽 데이터 스코프 목록")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="실행 메트릭 및 토큰/비용 텔레메트리")

    @property
    def matched(self) -> bool:
        """유효한 라우팅 대상 매칭 여부 (계산형 프로퍼티)."""
        return len(self.items) > 0

    @property
    def confidence(self) -> float:
        """Return deterministic structured-routing confidence."""
        return 1.0 if self.items else 0.0

    @property
    def sheets(self) -> List[str]:
        """Return the ordered union of routed sheets."""
        return list(dict.fromkeys(
            sheet for item in self.items for sheet in item.sheets
        ))

    @property
    def company_name(self) -> Optional[str]:
        """Return the primary routed company."""
        return self.items[0].company_name if self.items else None

    @property
    def company_scopes(self) -> List[CompanyScopeItemDTO]:
        """Return every structured company scope."""
        return self.items

    @property
    def target(self) -> Optional[str]:
        """Return the primary routed sheet."""
        return self.items[0].sheets[0] if (self.items and self.items[0].sheets) else None


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
        version="6",
    )
    input_model = LlmQueryRouterInputDTO
    config_model = LlmQueryRouterConfigDTO
    output_model = LlmQueryRouterOutputDTO

    def __init__(self, completion_client: Any) -> None:
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
        scopes_dump = [scope.model_dump(mode="json") for scope in items]

        return {
            "semantic_match": {
                "items": scopes_dump,
                "metrics": {
                    "kind": "llm_structured",
                    "model": cfg.model,
                    "latency_seconds": round(latency_sec, 3),
                    "api_usage": usage or {},
                    "estimated_cost_usd": round(cost_usd, 8),
                },
            }
        }


__all__ = [
    "CompanyScopeItemDTO",
    "LlmQueryRouterConfigDTO",
    "LlmQueryRouterInputDTO",
    "LlmQueryRouterOutputDTO",
    "LlmQueryRouterModule",
    "LlmRouterResponse",
    "RouterDecisionDTO",
]
