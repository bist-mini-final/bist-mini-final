"""LLM 호출, Pydantic 정형 출력 파싱, 에이전틱 도구 루프, 비용/토큰 집계를 전담하는 LLM 기본 클래스(BaseLLMModule).

자식 모듈의 중복 코드를 제거하고, `complete_structured()`, `complete_text()`, `complete_agentic()` 메서드를 통해
1줄 호출로 LLM 추론 및 성능 텔레메트리를 자동 집계합니다.
"""

from __future__ import annotations

import json
import logging
import time
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple, Type, TypeVar, Union

from pydantic import BaseModel, Field

from backend.providers.openai_pricing import calculate_openai_cost
from modules.common.base_module import (
    BaseModule,
    DocumentContextDTO,
    EmptyModuleConfigDTO,
    ModuleConfigDTO,
    ModuleConfigPreset,
    ModuleDefinition,
    ModuleDTO,
    ModuleInputDTO,
    ModuleTaskPolicy,
    QueryContextDTO,
    question_id_for,
)
from modules.common.exceptions import (
    DocumentParsingError,
    ModuleExecutionError,
    ModuleValidationError,
    PipelineBaseError,
    ProviderApiError,
    StorageError,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class ApiUsageDTO(ModuleDTO):
    prompt_tokens: Optional[int] = Field(default=0, ge=0, description="입력 토큰 수")
    completion_tokens: Optional[int] = Field(default=0, ge=0, description="출력 토큰 수")
    cached_tokens: Optional[int] = Field(default=0, ge=0, description="캐시 적중 토큰 수")
    reasoning_tokens: Optional[int] = Field(default=0, ge=0, description="추론 토큰 수")
    total_tokens: Optional[int] = Field(default=0, ge=0, description="전체 토큰 수")


class BaseLLMModule(BaseModule):
    """Specialized base class providing 1-line structured output generation, token usage & cost tracking."""

    def __init__(self, completion_client: Any) -> None:
        """Initialize with the Responses gateway owned by the composition root."""
        if completion_client is None:
            raise ValueError("BaseLLMModule에는 completion_client 주입이 필요합니다")
        self.completion_client = completion_client
        self._tool_schema_cache: Dict[Tuple[str, ...], List[Dict[str, Any]]] = {}
        self._structured_schema_cache: Dict[Type[BaseModel], Dict[str, Any]] = {}
        self.last_usage: Optional[Dict[str, int]] = None
        self.last_model: Optional[str] = None
        self.last_cost_usd: float = 0.0
        self.last_duration_seconds: float = 0.0

    @staticmethod
    def _strict_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize Pydantic JSON Schema to OpenAI strict-output requirements."""
        normalized = deepcopy(schema)

        def _visit(node: Any) -> None:
            if isinstance(node, dict):
                node.pop("default", None)
                properties = node.get("properties")
                if isinstance(properties, dict):
                    node["additionalProperties"] = False
                    node["required"] = list(properties)
                for value in node.values():
                    _visit(value)
            elif isinstance(node, list):
                for value in node:
                    _visit(value)

        _visit(normalized)
        return normalized

    @staticmethod
    def _usage_from_result(result: Any) -> ApiUsageDTO:
        usage_dict = getattr(result, "usage", {}) or {}
        return ApiUsageDTO(
            prompt_tokens=usage_dict.get("prompt_tokens", 0) or 0,
            completion_tokens=usage_dict.get("completion_tokens", 0) or 0,
            cached_tokens=usage_dict.get("cached_tokens", 0) or 0,
            reasoning_tokens=usage_dict.get("reasoning_tokens", 0) or 0,
            total_tokens=usage_dict.get("total_tokens", 0) or 0,
        )

    @staticmethod
    def _response_prompt(
        messages: List[Dict[str, Any]],
    ) -> Tuple[Optional[str], List[Dict[str, Any]]]:
        instructions: List[str] = []
        input_items: List[Dict[str, Any]] = []
        for message in messages:
            role = message.get("role")
            content = message.get("content", "")
            if role in {"system", "developer"}:
                if isinstance(content, str) and content:
                    instructions.append(content)
                continue
            input_items.append({"role": role, "content": content})
        return "\n\n".join(instructions) or None, input_items

    def complete_structured(
        self,
        messages_or_prompt: Union[str, List[Dict[str, str]]],
        response_model: Type[T],
        model: str,
        system_prompt: Optional[str] = None,
    ) -> Tuple[T, ApiUsageDTO, float, float]:
        """Call Responses with strict JSON Schema output and validate it as Pydantic."""
        if isinstance(messages_or_prompt, str):
            messages: List[Dict[str, str]] = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": messages_or_prompt})
        else:
            messages = messages_or_prompt

        schema_name = response_model.__name__[:64]
        response_schema = self._structured_schema_cache.get(response_model)
        if response_schema is None:
            response_schema = self._strict_schema(response_model.model_json_schema())
            self._structured_schema_cache[response_model] = response_schema
        instructions, input_items = self._response_prompt(messages)
        res = self.completion_client.create_response(
            model=model,
            instructions=instructions,
            input_items=input_items,
            text_format={
                "type": "json_schema",
                "name": schema_name,
                "strict": True,
                "schema": response_schema,
            },
        )
        parsed = response_model.model_validate_json(res.content.strip())

        usage = self._usage_from_result(res)
        cost = calculate_openai_cost(
            model_name=model,
            prompt_tokens=usage.prompt_tokens or 0,
            completion_tokens=usage.completion_tokens or 0,
            cached_tokens=usage.cached_tokens or 0,
        )
        latency = getattr(res, "latency_seconds", 0.0) or 0.0
        self.last_usage = usage.model_dump(mode="json")
        self.last_model = model
        self.last_cost_usd = cost
        self.last_duration_seconds = latency
        return parsed, usage, cost, latency

    def complete_text(
        self,
        messages_or_prompt: Union[str, List[Dict[str, str]]],
        model: str,
        system_prompt: Optional[str] = None,
    ) -> Tuple[str, ApiUsageDTO, float, float]:
        """Calls LLM and returns raw text content with usage metrics."""
        if isinstance(messages_or_prompt, str):
            messages: List[Dict[str, str]] = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": messages_or_prompt})
        else:
            messages = messages_or_prompt

        instructions, input_items = self._response_prompt(messages)
        res = self.completion_client.create_response(
            model=model,
            instructions=instructions,
            input_items=input_items,
        )
        content = res.content.strip()

        usage = self._usage_from_result(res)
        cost = calculate_openai_cost(
            model_name=model,
            prompt_tokens=usage.prompt_tokens or 0,
            completion_tokens=usage.completion_tokens or 0,
            cached_tokens=usage.cached_tokens or 0,
        )
        latency = getattr(res, "latency_seconds", 0.0) or 0.0
        self.last_usage = usage.model_dump(mode="json")
        self.last_model = model
        self.last_cost_usd = cost
        self.last_duration_seconds = latency
        return content, usage, cost, latency

    def complete_agentic(
        self,
        messages: List[Dict[str, Any]],
        tools_map: Dict[str, Any],
        model: str,
        max_iterations: int = 5,
        enable_tools: bool = True,
    ) -> Tuple[str, ApiUsageDTO, float, float]:
        """
        Executes a multi-turn tool-calling loop using standard LangChain BaseTool instances.
        
        Encapsulates:
        - OpenAI tool conversion
        - Multi-turn invoke loop with error-as-message feedback
        - Cumulative token usage aggregation
        - Automatic cost estimation and latency tracking
        """
        from langchain_core.utils.function_calling import convert_to_openai_tool

        started_at = time.perf_counter()
        openai_tools = None
        if enable_tools and tools_map:
            cache_key = tuple(tools_map)
            openai_tools = self._tool_schema_cache.get(cache_key)
            if openai_tools is None:
                openai_tools = []
                for tool in tools_map.values():
                    converted = convert_to_openai_tool(tool)
                    function = converted["function"]
                    openai_tools.append(
                        {
                            "type": "function",
                            "name": function["name"],
                            "description": function.get("description", ""),
                            "parameters": self._strict_schema(
                                function.get("parameters") or {
                                    "type": "object",
                                    "properties": {},
                                }
                            ),
                            "strict": True,
                        }
                    )
                self._tool_schema_cache[cache_key] = openai_tools

        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_cached_tokens = 0
        total_reasoning_tokens = 0
        total_cost = 0.0
        answer_text = ""

        instructions, input_items = self._response_prompt(messages)
        previous_response_id: Optional[str] = None

        for _ in range(max_iterations):
            res = self.completion_client.create_response(
                model=model,
                instructions=instructions,
                input_items=input_items,
                tools=openai_tools,
                previous_response_id=previous_response_id,
                store=True,
            )

            usage_dict = getattr(res, "usage", {}) or {}
            p_tok = usage_dict.get("prompt_tokens", 0) or 0
            c_tok = usage_dict.get("completion_tokens", 0) or 0
            ca_tok = usage_dict.get("cached_tokens", 0) or 0
            r_tok = usage_dict.get("reasoning_tokens", 0) or 0
            total_prompt_tokens += p_tok
            total_completion_tokens += c_tok
            total_cached_tokens += ca_tok
            total_reasoning_tokens += r_tok
            total_cost += calculate_openai_cost(
                model_name=model,
                prompt_tokens=p_tok,
                completion_tokens=c_tok,
                cached_tokens=ca_tok,
            )

            function_calls = getattr(res, "function_calls", ())
            if not function_calls:
                answer_text = res.content
                break

            input_items = []
            for function_call in function_calls:
                fn_name = function_call.get("name")
                fn_args_raw = function_call.get("arguments", "{}")
                if isinstance(fn_args_raw, str):
                    try:
                        fn_args = json.loads(fn_args_raw)
                    except (json.JSONDecodeError, TypeError):
                        fn_args = {}
                else:
                    fn_args = fn_args_raw or {}

                if fn_name in tools_map:
                    try:
                        tool_result_str = str(tools_map[fn_name].invoke(fn_args))
                    except Exception as invoke_err:
                        logger.warning("Tool %s invocation error: %s", fn_name, invoke_err)
                        tool_result_str = f"Tool execution failed: {invoke_err}"
                else:
                    tool_result_str = f"Unknown tool name: {fn_name}"

                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": function_call.get("call_id"),
                        "output": tool_result_str,
                    }
                )
            previous_response_id = res.response_id
        else:
            res = self.completion_client.create_response(
                model=model,
                instructions=instructions,
                input_items=input_items,
                previous_response_id=previous_response_id,
                store=True,
            )
            answer_text = res.content
            usage_dict = getattr(res, "usage", {}) or {}
            p_tok = usage_dict.get("prompt_tokens", 0) or 0
            c_tok = usage_dict.get("completion_tokens", 0) or 0
            ca_tok = usage_dict.get("cached_tokens", 0) or 0
            r_tok = usage_dict.get("reasoning_tokens", 0) or 0
            total_prompt_tokens += p_tok
            total_completion_tokens += c_tok
            total_cached_tokens += ca_tok
            total_reasoning_tokens += r_tok
            total_cost += calculate_openai_cost(
                model_name=model,
                prompt_tokens=p_tok,
                completion_tokens=c_tok,
                cached_tokens=ca_tok,
            )

        total_latency = time.perf_counter() - started_at
        api_usage = ApiUsageDTO(
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
            cached_tokens=total_cached_tokens,
            reasoning_tokens=total_reasoning_tokens,
            total_tokens=total_prompt_tokens + total_completion_tokens,
        )
        return answer_text, api_usage, total_cost, total_latency


__all__ = [
    "ApiUsageDTO",
    "BaseLLMModule",
    "BaseModule",
    "DocumentContextDTO",
    "DocumentParsingError",
    "EmptyModuleConfigDTO",
    "ModuleConfigDTO",
    "ModuleConfigPreset",
    "ModuleDTO",
    "ModuleDefinition",
    "ModuleExecutionError",
    "ModuleInputDTO",
    "ModuleTaskPolicy",
    "ModuleValidationError",
    "PipelineBaseError",
    "ProviderApiError",
    "QueryContextDTO",
    "StorageError",
    "calculate_openai_cost",
    "question_id_for",
]
