from __future__ import annotations

"""Workflow module wrapper for the isolated semantic query matcher."""

import json
import time
from typing import Optional, Any, Dict, List, Optional, cast

from pydantic import BaseModel, Field

from backend.providers.embeddings.factory import EmbeddingEncoder, get_embedding_encoder
from backend.providers.llm.chat_completion import ChatCompletionClient, ChatCompletionError
from backend.providers.llm.cost import calculate_openai_cost
from backend.semantic_matching.catalog import QueryExample, load_examples
from backend.semantic_matching.matcher import SemanticQueryMatcher
from modules.common.base_module import BaseModule, ModuleConfigDTO, ModuleDefinition, ModuleDTO, ModuleExecutionError, ModuleInputDTO, QueryContextDTO
from modules.common.config import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_ROUTER_MODEL,
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


# ==============================================================================
# 2. LLM Query Router Module
# ==============================================================================

class LlmQueryRouterInput(ModuleInputDTO):
    query_context: QueryContextDTO


class LlmQueryRouterConfig(ModuleConfigDTO):
    model: str = Field(default=DEFAULT_ROUTER_MODEL)


class LlmQueryRouterExecution(LlmQueryRouterInput, LlmQueryRouterConfig):
    """Runtime union of the graph input and node configuration."""


class LlmQueryRouterOutput(ModuleDTO):
    semantic_match: SemanticQueryMatchOutput


def _catalog_prompt(examples: tuple[QueryExample, ...]) -> str:
    targets: Dict[str, set[str]] = {}
    for example in examples:
        targets.setdefault(example.target, set()).update(example.sheets)
    choices = [
        {"target": target, "sheets": sorted(sheets)}
        for target, sheets in sorted(targets.items())
    ]
    return (
        "You route spreadsheet questions to a known data source. "
        "Return JSON only: {\"target\": string|null, \"reason\": string}. "
        "Choose target only from this catalog; use null if none fits.\n"
        + json.dumps(choices, ensure_ascii=False)
    )


class LlmQueryRouterModule(BaseModule):
    definition = ModuleDefinition(
        type="llm_query_router",
        label="LLM Query Router",
        category="Logic",
        description="LLM이 질문에 맞는 source/sheet 범위를 선택합니다. 시맨틱 라우터의 A/B 비교 대상입니다.",
        inputs=["query_context"],
        outputs=["semantic_match"],
        config_fields=["model"],
        version="1",
    )
    input_model = LlmQueryRouterInput
    config_model = LlmQueryRouterConfig
    execution_model = LlmQueryRouterExecution
    output_model = LlmQueryRouterOutput

    def __init__(self, completion_client: Optional[ChatCompletionClient] = None) -> None:
        self.completion_client = completion_client or ChatCompletionClient()

    def execute(
        self,
        input_data: LlmQueryRouterInput,
        config: Optional[LlmQueryRouterConfig] = None,
    ) -> Dict[str, Any]:
        if config is None and isinstance(input_data, LlmQueryRouterExecution):
            cfg = input_data
        else:
            cfg = config or LlmQueryRouterConfig()
        examples = load_examples()
        valid_sheets: Dict[str, List[str]] = {}
        for example in examples:
            valid_sheets.setdefault(example.target, [])
            valid_sheets[example.target] = sorted(set(valid_sheets[example.target]) | set(example.sheets))
        started = time.perf_counter()
        try:
            result = self.completion_client.complete_with_metadata(
                cfg.model,
                [
                    {"role": "system", "content": _catalog_prompt(examples)},
                    {"role": "user", "content": input_data.query_context.question_text},
                ],
            )
            document = json.loads(result.content.strip().removeprefix("```json").removesuffix("```").strip())
        except (ChatCompletionError, ValueError, TypeError, json.JSONDecodeError) as error:
            raise ModuleExecutionError(f"LLM router failed: {error}") from error
        target = document.get("target") if isinstance(document, dict) else None
        if target not in valid_sheets:
            target = None
        reason = str(document.get("reason") or "LLM route decision") if isinstance(document, dict) else "Invalid LLM route response"
        usage = result.usage
        estimated_cost = (
            (usage.get("prompt_tokens", 0) - usage.get("cached_tokens", 0)) * 1.0
            + usage.get("cached_tokens", 0) * 0.1
            + usage.get("completion_tokens", 0) * 6.0
        ) / 1_000_000
        return {"semantic_match": {
            "matched": target is not None,
            "target": target,
            "confidence": 1.0 if target else 0.0,
            "sheets": valid_sheets.get(target, []) if target is not None else [],
            "reason": reason,
            "matches": [],
            "metrics": {
                "kind": "llm",
                "model": cfg.model,
                "latency_seconds": round(result.latency_seconds or time.perf_counter() - started, 3),
                "api_usage": usage,
                "estimated_cost_usd": round(estimated_cost, 6),
            },
        }}


__all__ = [
    "LlmQueryRouterConfig",
    "LlmQueryRouterExecution",
    "LlmQueryRouterInput",
    "LlmQueryRouterModule",
    "LlmQueryRouterOutput",
    "RouterMetricsDTO",
    "SemanticMatchItemDTO",
    "SemanticQueryMatchOutput",
    "SemanticQueryMatcherConfig",
    "SemanticQueryMatcherExecution",
    "SemanticQueryMatcherInput",
    "SemanticQueryMatcherModule",
    "SemanticQueryMatcherWorkflowOutput",
]

