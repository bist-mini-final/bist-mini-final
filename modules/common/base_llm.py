"""LLM 호출, Pydantic 정형 출력 파싱, 에이전틱 도구 루프, 비용/토큰 집계를 전담하는 LLM 기본 클래스(BaseLLMModule).

자식 모듈의 중복 코드를 제거하고, `complete_structured()`, `complete_text()`, `complete_agentic()` 메서드를 통해
1줄 호출로 LLM 추론 및 성능 텔레메트리를 자동 집계합니다.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Type, TypeVar, Union, cast

from pydantic import BaseModel, Field

from backend.platform.openai.pricing import calculate_openai_cost
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


@dataclass(slots=True)
class _UsageAccumulator:
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    cost_usd: float = 0.0

    def record(self, response: Any) -> None:
        usage = getattr(response, "usage", {}) or {}
        prompt_tokens = usage.get("prompt_tokens", 0) or 0
        completion_tokens = usage.get("completion_tokens", 0) or 0
        cached_tokens = usage.get("cached_tokens", 0) or 0
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.cached_tokens += cached_tokens
        self.reasoning_tokens += usage.get("reasoning_tokens", 0) or 0
        self.cost_usd += calculate_openai_cost(
            model_name=self.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
        )

    def usage(self) -> ApiUsageDTO:
        return ApiUsageDTO(
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            cached_tokens=self.cached_tokens,
            reasoning_tokens=self.reasoning_tokens,
            total_tokens=self.prompt_tokens + self.completion_tokens,
        )


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

    @staticmethod
    def _messages(
        messages_or_prompt: Union[str, List[Dict[str, str]]],
        system_prompt: Optional[str],
    ) -> List[Dict[str, str]]:
        if not isinstance(messages_or_prompt, str):
            return messages_or_prompt
        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": messages_or_prompt})
        return messages

    def _structured_format(self, response_model: Type[BaseModel]) -> Dict[str, Any]:
        response_schema = self._structured_schema_cache.get(response_model)
        if response_schema is None:
            response_schema = self._strict_schema(response_model.model_json_schema())
            self._structured_schema_cache[response_model] = response_schema
        return {
            "type": "json_schema",
            "name": response_model.__name__[:64],
            "strict": True,
            "schema": response_schema,
        }

    def _completion_metrics(
        self,
        result: Any,
        model: str,
    ) -> Tuple[ApiUsageDTO, float, float]:
        usage = self._usage_from_result(result)
        cost = calculate_openai_cost(
            model_name=model,
            prompt_tokens=usage.prompt_tokens or 0,
            completion_tokens=usage.completion_tokens or 0,
            cached_tokens=usage.cached_tokens or 0,
        )
        latency = getattr(result, "latency_seconds", 0.0) or 0.0
        self._remember_metrics(model, usage, cost, latency)
        return usage, cost, latency

    def _remember_metrics(
        self,
        model: str,
        usage: ApiUsageDTO,
        cost: float,
        latency: float,
    ) -> None:
        self.last_usage = usage.model_dump(mode="json")
        self.last_model = model
        self.last_cost_usd = cost
        self.last_duration_seconds = latency

    def _openai_tools(
        self,
        tools_map: Dict[str, Any],
        enable_tools: bool,
    ) -> Optional[List[Dict[str, Any]]]:
        if not enable_tools or not tools_map:
            return None
        cache_key = tuple(tools_map)
        cached = self._tool_schema_cache.get(cache_key)
        if cached is not None:
            return cached

        from langchain_core.utils.function_calling import convert_to_openai_tool

        converted_tools: List[Dict[str, Any]] = []
        for tool in tools_map.values():
            function = convert_to_openai_tool(tool)["function"]
            converted_tools.append(
                {
                    "type": "function",
                    "name": function["name"],
                    "description": function.get("description", ""),
                    "parameters": self._strict_schema(
                        function.get("parameters") or {"type": "object", "properties": {}}
                    ),
                    "strict": True,
                }
            )
        self._tool_schema_cache[cache_key] = converted_tools
        return converted_tools

    @staticmethod
    def _tool_arguments(function_call: Dict[str, Any]) -> Any:
        raw_arguments = function_call.get("arguments", "{}")
        if not isinstance(raw_arguments, str):
            return raw_arguments or {}
        try:
            return json.loads(raw_arguments)
        except (json.JSONDecodeError, TypeError):
            return {}

    @staticmethod
    def _tool_output_item(function_call: Dict[str, Any], output: str) -> Dict[str, Any]:
        return {
            "type": "function_call_output",
            "call_id": function_call.get("call_id"),
            "output": output,
        }

    def _sync_tool_outputs(
        self,
        function_calls: Tuple[Dict[str, Any], ...],
        tools_map: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        outputs: List[Dict[str, Any]] = []
        for function_call in function_calls:
            name = function_call.get("name")
            if name not in tools_map:
                output = f"Unknown tool name: {name}"
            else:
                try:
                    output = str(tools_map[name].invoke(self._tool_arguments(function_call)))
                except Exception as error:
                    logger.warning("Tool %s invocation error: %s", name, error)
                    output = f"Tool execution failed: {error}"
            outputs.append(self._tool_output_item(function_call, output))
        return outputs

    async def _async_tool_outputs(
        self,
        function_calls: Tuple[Dict[str, Any], ...],
        tools_map: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        outputs: List[Dict[str, Any]] = []
        for function_call in function_calls:
            name = function_call.get("name")
            if name not in tools_map:
                output = f"Unknown tool name: {name}"
            else:
                tool = tools_map[name]
                arguments = self._tool_arguments(function_call)
                try:
                    async_invoke = getattr(tool, "ainvoke", None)
                    result = (
                        await cast(Any, async_invoke)(arguments)
                        if callable(async_invoke)
                        else await asyncio.to_thread(tool.invoke, arguments)
                    )
                    output = str(result)
                except Exception as error:
                    logger.warning("Tool %s invocation error: %s", name, error)
                    output = f"Tool execution failed: {error}"
            outputs.append(self._tool_output_item(function_call, output))
        return outputs

    def _agentic_result(
        self,
        answer: str,
        accumulator: _UsageAccumulator,
        started_at: float,
    ) -> Tuple[str, ApiUsageDTO, float, float]:
        latency = time.perf_counter() - started_at
        usage = accumulator.usage()
        self._remember_metrics(accumulator.model, usage, accumulator.cost_usd, latency)
        return answer, usage, accumulator.cost_usd, latency

    def complete_structured(
        self,
        messages_or_prompt: Union[str, List[Dict[str, str]]],
        response_model: Type[T],
        model: str,
        system_prompt: Optional[str] = None,
    ) -> Tuple[T, ApiUsageDTO, float, float]:
        """Call Responses with strict JSON Schema output and validate it as Pydantic."""
        messages = self._messages(messages_or_prompt, system_prompt)
        instructions, input_items = self._response_prompt(messages)
        res = self.completion_client.create_response(
            model=model,
            instructions=instructions,
            input_items=input_items,
            text_format=self._structured_format(response_model),
        )
        parsed = response_model.model_validate_json(res.content.strip())
        usage, cost, latency = self._completion_metrics(res, model)
        return parsed, usage, cost, latency

    async def complete_structured_async(
        self,
        messages_or_prompt: Union[str, List[Dict[str, str]]],
        response_model: Type[T],
        model: str,
        system_prompt: Optional[str] = None,
    ) -> Tuple[T, ApiUsageDTO, float, float]:
        """Native async equivalent of :meth:`complete_structured`."""
        messages = self._messages(messages_or_prompt, system_prompt)
        instructions, input_items = self._response_prompt(messages)
        res = await self.completion_client.create_response_async(
            model=model,
            instructions=instructions,
            input_items=input_items,
            text_format=self._structured_format(response_model),
        )
        parsed = response_model.model_validate_json(res.content.strip())
        usage, cost, latency = self._completion_metrics(res, model)
        return parsed, usage, cost, latency

    def complete_text(
        self,
        messages_or_prompt: Union[str, List[Dict[str, str]]],
        model: str,
        system_prompt: Optional[str] = None,
    ) -> Tuple[str, ApiUsageDTO, float, float]:
        """Calls LLM and returns raw text content with usage metrics."""
        messages = self._messages(messages_or_prompt, system_prompt)
        instructions, input_items = self._response_prompt(messages)
        res = self.completion_client.create_response(
            model=model,
            instructions=instructions,
            input_items=input_items,
        )
        content = res.content.strip()
        usage, cost, latency = self._completion_metrics(res, model)
        return content, usage, cost, latency

    async def complete_text_async(
        self,
        messages_or_prompt: Union[str, List[Dict[str, str]]],
        model: str,
        system_prompt: Optional[str] = None,
    ) -> Tuple[str, ApiUsageDTO, float, float]:
        """Call Responses without blocking the workflow event loop."""
        messages = self._messages(messages_or_prompt, system_prompt)
        instructions, input_items = self._response_prompt(messages)
        res = await self.completion_client.create_response_async(
            model=model,
            instructions=instructions,
            input_items=input_items,
        )
        content = res.content.strip()
        usage, cost, latency = self._completion_metrics(res, model)
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
        started_at = time.perf_counter()
        openai_tools = self._openai_tools(tools_map, enable_tools)
        accumulator = _UsageAccumulator(model)
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
            accumulator.record(res)
            function_calls = getattr(res, "function_calls", ())
            if not function_calls:
                answer_text = res.content
                break
            input_items = self._sync_tool_outputs(function_calls, tools_map)
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
            accumulator.record(res)
        return self._agentic_result(answer_text, accumulator, started_at)

    async def complete_agentic_async(
        self,
        messages: List[Dict[str, Any]],
        tools_map: Dict[str, Any],
        model: str,
        max_iterations: int = 5,
        enable_tools: bool = True,
    ) -> Tuple[str, ApiUsageDTO, float, float]:
        """Run the Responses tool loop with native async provider and tool calls."""
        started_at = time.perf_counter()
        openai_tools = self._openai_tools(tools_map, enable_tools)
        accumulator = _UsageAccumulator(model)
        answer_text = ""
        instructions, input_items = self._response_prompt(messages)
        previous_response_id: Optional[str] = None

        for _ in range(max_iterations):
            res = await self.completion_client.create_response_async(
                model=model,
                instructions=instructions,
                input_items=input_items,
                tools=openai_tools,
                previous_response_id=previous_response_id,
                store=True,
            )
            accumulator.record(res)
            function_calls = getattr(res, "function_calls", ())
            if not function_calls:
                answer_text = res.content
                break
            input_items = await self._async_tool_outputs(function_calls, tools_map)
            previous_response_id = res.response_id
        else:
            res = await self.completion_client.create_response_async(
                model=model,
                instructions=instructions,
                input_items=input_items,
                previous_response_id=previous_response_id,
                store=True,
            )
            answer_text = res.content
            accumulator.record(res)
        return self._agentic_result(answer_text, accumulator, started_at)


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
