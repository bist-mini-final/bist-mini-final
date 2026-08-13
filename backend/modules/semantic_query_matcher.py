"""Workflow module wrapper for the isolated semantic query matcher."""

import time
from typing import Any, Dict, List, Optional, cast

from pydantic import BaseModel, Field

from ..embedding_factory import EmbeddingEncoder, get_embedding_encoder
from ..semantic_matching.matcher import SemanticQueryMatcher
from .base import ExecutableModule, ModuleDefinition, ModuleDTO
from .embedder import EMBEDDING_MODEL_OPTIONS


class SemanticQueryMatcherInput(ModuleDTO):
    question_text: str = Field(min_length=1)
    model: str = Field(default="text-embedding-3-small", json_schema_extra={"enum": EMBEDDING_MODEL_OPTIONS})
    threshold: float = Field(default=0.74, ge=0, le=1)
    top_k: int = Field(default=5, ge=1, le=20)
    vote_margin: float = Field(default=0.05, ge=0, le=1)


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
    metrics: RouterMetricsDTO = Field(default_factory=_legacy_router_metrics)


class SemanticQueryMatcherWorkflowOutput(ModuleDTO):
    """Named workflow port wrapper; the retriever receives its inner value."""

    semantic_match: SemanticQueryMatchOutput


class SemanticQueryMatcherModule(ExecutableModule):
    definition = ModuleDefinition(
        type="semantic_query_matcher",
        label="Semantic Query Matcher",
        category="Logic",
        description="예시 질의 임베딩으로 대상 시트를 판별하고, 불확실하면 전체 검색을 유지합니다.",
        inputs=["question_text"],
        outputs=["semantic_match"],
        config_fields=["model", "threshold", "top_k", "vote_margin"],
        raw_output=False,
        version="1",
    )
    input_model = SemanticQueryMatcherInput
    output_model = SemanticQueryMatcherWorkflowOutput

    def __init__(self, encoder: Optional[EmbeddingEncoder] = None) -> None:
        self.encoder = encoder
        self._matchers: Dict[str, SemanticQueryMatcher] = {}

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        input_data = cast(SemanticQueryMatcherInput, payload)
        matcher = self._matchers.get(input_data.model)
        if matcher is None:
            matcher = SemanticQueryMatcher(
                get_embedding_encoder(input_data.model, override_encoder=self.encoder)
            )
            self._matchers[input_data.model] = matcher
        started_at = time.perf_counter()
        decision = matcher.route(
            input_data.question_text, input_data.model, input_data.threshold,
            input_data.top_k, input_data.vote_margin,
        )
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
                "metrics": {
                    "kind": "semantic",
                    "model": input_data.model,
                    "latency_seconds": round(time.perf_counter() - started_at, 3),
                    "api_usage": {},
                    "estimated_cost_usd": 0,
                },
            }
        }
