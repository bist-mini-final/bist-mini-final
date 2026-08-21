from __future__ import annotations

"""Workflow module wrapper for the isolated semantic query matcher."""

import time
from typing import Optional, Any, Dict, List, Optional, cast

from pydantic import BaseModel, Field

from backend.providers.embeddings.factory import EmbeddingEncoder, get_embedding_encoder
from backend.providers.llm.cost import calculate_openai_cost
from backend.semantic_matching.matcher import SemanticQueryMatcher
from modules.common.base_module import BaseModule, ModuleConfigDTO, ModuleDefinition, ModuleDTO, ModuleInputDTO, QueryContextDTO
from modules.common.config import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_SEMANTIC_THRESHOLD,
    DEFAULT_SEMANTIC_TOP_K,
    DEFAULT_SEMANTIC_VOTE_MARGIN,
    EMBEDDING_MODEL_OPTIONS,
)


class SemanticQueryMatcherInput(ModuleInputDTO):
    query_context: QueryContextDTO


class SemanticQueryMatcherConfig(ModuleConfigDTO):
    model: str = Field(
        default=DEFAULT_EMBEDDING_MODEL,
        json_schema_extra=cast(Any, {"enum": list(EMBEDDING_MODEL_OPTIONS), "options": list(EMBEDDING_MODEL_OPTIONS)}),
    )
    threshold: float = Field(default=DEFAULT_SEMANTIC_THRESHOLD, ge=0, le=1)
    top_k: int = Field(default=DEFAULT_SEMANTIC_TOP_K, ge=1, le=20)
    vote_margin: float = Field(default=DEFAULT_SEMANTIC_VOTE_MARGIN, ge=0, le=1)


class SemanticQueryMatcherExecution(SemanticQueryMatcherInput, SemanticQueryMatcherConfig):
    """Runtime union of the graph input and node configuration."""


class SemanticMatchItemDTO(ModuleDTO):
    example_id: str
    question: str
    target: str
    sheets: List[str]
    similarity: float


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
        description="예시 질의 임베딩으로 대상 시트를 판별하고, 불확실하면 전체 검색을 유지합니다.",
        inputs=["query_context"],
        outputs=["semantic_match"],
        config_fields=["model", "threshold", "top_k", "vote_margin"],
        raw_output=False,
        version="1",
    )
    input_model = SemanticQueryMatcherInput
    config_model = SemanticQueryMatcherConfig
    execution_model = SemanticQueryMatcherExecution
    output_model = SemanticQueryMatcherWorkflowOutput

    def __init__(self, encoder: Optional[EmbeddingEncoder] = None) -> None:
        self.encoder = encoder
        self._matchers: Dict[str, SemanticQueryMatcher] = {}

    def execute(
        self,
        input_data: SemanticQueryMatcherInput,
        config: Optional[SemanticQueryMatcherConfig] = None,
    ) -> Dict[str, Any]:
        if config is None and isinstance(input_data, SemanticQueryMatcherExecution):
            cfg = input_data
        else:
            cfg = config or SemanticQueryMatcherConfig()
        matcher = self._matchers.get(cfg.model)
        if matcher is None:
            matcher = SemanticQueryMatcher(
                get_embedding_encoder(cfg.model, override_encoder=self.encoder)
            )
            self._matchers[cfg.model] = matcher
        started_at = time.perf_counter()
        decision = matcher.route(
            input_data.query_context.question_text, cfg.model, cfg.threshold,
            cfg.top_k, cfg.vote_margin,
        )
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
        return {
            "semantic_match": {
                "matched": decision.target is not None,
                "target": decision.target,
                "confidence": round(decision.confidence, 10),
                "sheets": list(decision.sheets),
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
                    "kind": "semantic",
                    "model": cfg.model,
                    "latency_seconds": round(time.perf_counter() - started_at, 3),
                    "api_usage": usage,
                    "estimated_cost_usd": round(estimated_cost, 8),
                },
            }
        }
