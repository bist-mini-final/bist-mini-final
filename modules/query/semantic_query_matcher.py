"""Workflow module wrapper for the isolated semantic query matcher and LLM router."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence

from pydantic import Field

from backend.providers.embeddings.factory import EmbeddingEncoder, get_embedding_encoder
from backend.providers.llm.cost import calculate_openai_cost
from backend.semantic_matching.catalog import QueryExample
from backend.semantic_matching.matcher import SemanticQueryMatcher
from modules.common.base_embedder import (
    BaseModule,
    EmbeddingConfigDTO,
    ModuleDefinition,
    ModuleDTO,
    ModuleInputDTO,
    QueryContextDTO,
)
from modules.common.config import (
    DEFAULT_SEMANTIC_THRESHOLD,
    DEFAULT_SEMANTIC_TOP_K,
    DEFAULT_SEMANTIC_VOTE_MARGIN,
)


class SemanticQueryMatcherInput(ModuleInputDTO):
    query_context: QueryContextDTO


class SemanticQueryMatcherConfig(EmbeddingConfigDTO):
    threshold: float = Field(default=DEFAULT_SEMANTIC_THRESHOLD, ge=0, le=1)
    top_k: int = Field(default=DEFAULT_SEMANTIC_TOP_K, ge=1, le=20)
    vote_margin: float = Field(default=DEFAULT_SEMANTIC_VOTE_MARGIN, ge=0, le=1)


class SemanticMatchItemDTO(ModuleDTO):
    example_id: str
    question: str
    target: str
    sheets: List[str]
    similarity: float


class CompanyScopeItemDTO(ModuleDTO):
    raw_mention: str = Field(description="질문 내 원본 기업/엔티티 언급 (예: '삼전', '비스텔리젼스')")
    canonical_name: str = Field(description="정규화된 기업명 (예: '삼성전자', '비스텔리젼스')")
    matched_score: float = Field(default=1.0, ge=0.0, le=1.0, description="엔티티 매칭 점수")
    target_topics: List[str] = Field(default_factory=list, description="해당 기업에 할당된 질문 키워드/지표")
    suggested_sheets: List[str] = Field(default_factory=list, description="해당 기업/토픽에 매핑되는 대상 시트")


class RouterMetricsDTO(ModuleDTO):
    kind: str
    model: str
    latency_seconds: float = Field(ge=0)
    api_usage: Dict[str, int] = Field(default_factory=dict)
    estimated_cost_usd: float = Field(default=0, ge=0)


def _legacy_router_metrics() -> RouterMetricsDTO:
    """Keep saved workflows and tests created before benchmark telemetry valid."""
    return RouterMetricsDTO(
        kind="unknown", model="unknown", latency_seconds=0,
    )


class SemanticQueryMatchOutput(ModuleDTO):
    matched: bool
    target: Optional[str]
    confidence: float
    sheets: List[str]
    reason: str
    company_name: Optional[str] = Field(default=None, description="질문 또는 컨텍스트에서 추출된 단일/대표 대상 기업명")
    company_scopes: List[CompanyScopeItemDTO] = Field(default_factory=list, description="질문에서 추출된 기업별 세부 인텐트 스코프 목록")
    matches: List[SemanticMatchItemDTO]
    query_type: Optional[int] = None
    subqueries: List[str] = Field(default_factory=list)
    metrics: RouterMetricsDTO = Field(default_factory=_legacy_router_metrics)


class SemanticQueryMatcherWorkflowOutput(ModuleDTO):
    """Named workflow port wrapper; the retriever receives its inner value."""

    semantic_match: SemanticQueryMatchOutput


class SemanticQueryMatcherModule(BaseModule):
    definition = ModuleDefinition(
        type="semantic_query_matcher",
        label="Semantic Query Matcher",
        category="Logic",
        description="질문이 기존 쿼리 뱅크 예제와 매칭되는지 코사인 유사도로 판정하여 대상 시트를 라우팅합니다.",
        inputs=["query_context"],
        outputs=["semantic_match"],
        config_fields=["threshold", "top_k", "vote_margin", "model", "dimension", "batch_size"],
        version="3",
    )
    input_model = SemanticQueryMatcherInput
    config_model = SemanticQueryMatcherConfig
    output_model = SemanticQueryMatcherWorkflowOutput

    def __init__(
        self,
        matcher: Optional[SemanticQueryMatcher] = None,
        encoder: Optional[EmbeddingEncoder] = None,
        examples: Optional[Sequence[QueryExample]] = None,
    ) -> None:
        super().__init__()
        self.encoder = encoder
        self.examples = examples
        self.matcher = matcher
        self._matchers: Dict[str, SemanticQueryMatcher] = {}

    def _resolved_matcher(self, config: SemanticQueryMatcherConfig) -> SemanticQueryMatcher:
        if self.matcher is not None:
            return self.matcher

        model = config.model
        matcher = self._matchers.get(model)
        if matcher is None:
            encoder = get_embedding_encoder(
                model_name=model,
                override_encoder=self.encoder,
            )
            examples = tuple(self.examples) if self.examples is not None else None
            matcher = SemanticQueryMatcher(
                encoder=encoder,
                examples=examples,
            )
            self._matchers[model] = matcher
        return matcher

    def execute(
        self,
        input_data: SemanticQueryMatcherInput,
        config: Optional[SemanticQueryMatcherConfig] = None,
    ) -> Dict[str, Any]:
        cfg = config or SemanticQueryMatcherConfig()
        matcher = self._resolved_matcher(cfg)
        started = time.perf_counter()
        decision = matcher.route(
            question=input_data.query_context.question_text,
            model=cfg.model,
            threshold=cfg.threshold,
            top_k=cfg.top_k,
            vote_margin=cfg.vote_margin,
        )
        latency = time.perf_counter() - started

        usage = getattr(matcher.encoder, "last_usage", None)
        if not isinstance(usage, dict):
            usage = {}
        self.last_usage = usage or None
        self.last_model = cfg.model

        estimated_cost = calculate_openai_cost(
            model_name=cfg.model,
            prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
            completion_tokens=0,
            cached_tokens=0,
        ) if usage else 0.0

        model_name = getattr(matcher.encoder, "model_name", cfg.model)

        return {"semantic_match": {
            "matched": decision.target is not None,
            "target": decision.target,
            "confidence": round(decision.confidence, 10),
            "sheets": list(decision.sheets),
            "company_name": decision.company_name,
            "company_scopes": [],
            "reason": decision.reason,
            "matches": [
                {
                    "example_id": match.example_id,
                    "question": match.question,
                    "target": match.target,
                    "sheets": list(match.sheets),
                    "similarity": round(match.similarity, 10),
                }
                for match in decision.matches
            ],
            "query_type": decision.query_type,
            "subqueries": list(decision.subqueries),
            "metrics": {
                "kind": "cosine",
                "model": model_name,
                "latency_seconds": round(latency, 3),
                "api_usage": usage,
                "estimated_cost_usd": round(estimated_cost, 8),
            },
        }}


# Backward compatibility aliases
SemanticQueryMatcherExecution = SemanticQueryMatcherInput

__all__ = [
    "CompanyScopeItemDTO",
    "RouterMetricsDTO",
    "SemanticMatchItemDTO",
    "SemanticQueryMatchOutput",
    "SemanticQueryMatcherConfig",
    "SemanticQueryMatcherExecution",
    "SemanticQueryMatcherInput",
    "SemanticQueryMatcherModule",
    "SemanticQueryMatcherWorkflowOutput",
]
