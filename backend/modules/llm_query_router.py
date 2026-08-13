"""LLM-based counterpart to the embedding semantic query matcher.

The module deliberately returns the same DTO as ``semantic_query_matcher`` so
that an experiment can swap only the router node and keep retrieval, context,
and reader nodes identical.
"""

import json
import time
from typing import Any, Dict, List, Optional, cast

from pydantic import BaseModel, Field

from ..chat_completion import ChatCompletionClient, ChatCompletionError
from ..semantic_matching.catalog import QueryExample, load_examples
from .base import ExecutableModule, ModuleDefinition, ModuleDTO, ModuleExecutionError
from .semantic_query_matcher import (
    RouterMetricsDTO,
    SemanticMatchItemDTO,
    SemanticQueryMatchOutput,
)


class LlmQueryRouterInput(ModuleDTO):
    question_text: str = Field(min_length=1)
    model: str = Field(default="gpt-5.6-luna")


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


class LlmQueryRouterModule(ExecutableModule):
    definition = ModuleDefinition(
        type="llm_query_router",
        label="LLM Query Router",
        category="Logic",
        description="LLM이 질문에 맞는 source/sheet 범위를 선택합니다. 시맨틱 라우터의 A/B 비교 대상입니다.",
        inputs=["question_text"],
        outputs=["semantic_match"],
        config_fields=["model"],
        version="1",
    )
    input_model = LlmQueryRouterInput
    output_model = LlmQueryRouterOutput

    def __init__(self, completion_client: Optional[ChatCompletionClient] = None) -> None:
        self.completion_client = completion_client or ChatCompletionClient()

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        input_data = cast(LlmQueryRouterInput, payload)
        examples = load_examples()
        valid_sheets: Dict[str, List[str]] = {}
        for example in examples:
            valid_sheets.setdefault(example.target, [])
            valid_sheets[example.target] = sorted(set(valid_sheets[example.target]) | set(example.sheets))
        started = time.perf_counter()
        try:
            result = self.completion_client.complete_with_metadata(
                input_data.model,
                [
                    {"role": "system", "content": _catalog_prompt(examples)},
                    {"role": "user", "content": input_data.question_text},
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
            "sheets": valid_sheets.get(target, []),
            "reason": reason,
            "matches": [],
            "metrics": {
                "kind": "llm",
                "model": input_data.model,
                "latency_seconds": round(result.latency_seconds or time.perf_counter() - started, 3),
                "api_usage": usage,
                "estimated_cost_usd": round(estimated_cost, 6),
            },
        }}
