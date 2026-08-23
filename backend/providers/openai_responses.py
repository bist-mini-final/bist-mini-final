"""Application gateway for text, tool, and vision Responses API calls."""

from __future__ import annotations

import base64
import mimetypes
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import httpx
from openai import OpenAIError

from backend.providers.openai_provider import (
    OpenAIProvider,
    OpenAIProviderError,
    project_env_value,
)

ReasoningEffort = Literal["none", "low", "medium", "high", "xhigh", "max"]


class OpenAIResponsesError(RuntimeError):
    """Raised when an OpenAI Responses request cannot complete."""


@dataclass(frozen=True)
class OpenAIResponseResult:
    """Normalized Responses result used by the application runtime."""

    response_id: str
    content: str
    usage: dict[str, int]
    latency_seconds: float
    function_calls: tuple[dict[str, Any], ...] = ()


def _image_data_url(image_path: Path) -> str:
    mime_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _output_text(document: dict[str, Any]) -> str:
    direct = document.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    texts: list[str] = []
    refusals: list[str] = []
    for output_item in document.get("output") or []:
        if not isinstance(output_item, dict):
            continue
        for content_item in output_item.get("content") or []:
            if not isinstance(content_item, dict):
                continue
            item_type = content_item.get("type")
            value = content_item.get("text")
            if item_type == "output_text" and isinstance(value, str) and value.strip():
                texts.append(value.strip())
            refusal = content_item.get("refusal")
            if item_type == "refusal" and isinstance(refusal, str) and refusal.strip():
                refusals.append(refusal.strip())
    if texts:
        return "\n".join(texts)
    if refusals:
        raise OpenAIResponsesError("OpenAI API가 요청을 거절했습니다")
    return ""


def _function_calls(document: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "call_id": item.get("call_id"),
            "name": item.get("name"),
            "arguments": item.get("arguments", "{}"),
        }
        for item in document.get("output") or []
        if isinstance(item, dict) and item.get("type") == "function_call"
    )


def _usage(document: dict[str, Any]) -> dict[str, int]:
    raw_usage = document.get("usage") or {}
    input_details = raw_usage.get("input_tokens_details") or {}
    output_details = raw_usage.get("output_tokens_details") or {}
    return {
        "prompt_tokens": int(raw_usage.get("input_tokens", 0) or 0),
        "completion_tokens": int(raw_usage.get("output_tokens", 0) or 0),
        "cached_tokens": int(input_details.get("cached_tokens", 0) or 0),
        "reasoning_tokens": int(output_details.get("reasoning_tokens", 0) or 0),
        "total_tokens": int(raw_usage.get("total_tokens", 0) or 0),
    }


class OpenAIResponsesClient:
    """Responses gateway backed by the process-scoped official SDK client."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float = 30,
        http_client: httpx.Client | None = None,
        *,
        provider: OpenAIProvider | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self._owns_provider = provider is None
        self.provider = provider or OpenAIProvider(
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            http_client=http_client,
        )

    def create_response(
        self,
        *,
        model: str,
        input_items: list[dict[str, Any]],
        instructions: str | None = None,
        text_format: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
        previous_response_id: str | None = None,
        reasoning_effort: ReasoningEffort = "none",
        max_output_tokens: int | None = None,
        timeout_seconds: float | None = None,
        store: bool = False,
    ) -> OpenAIResponseResult:
        request: dict[str, Any] = {
            "model": model,
            "input": input_items,
            "store": store,
        }
        if reasoning_effort is not None:
            request["reasoning"] = {"effort": reasoning_effort}
        if instructions:
            request["instructions"] = instructions
        if text_format is not None:
            request["text"] = {"format": text_format}
        if tools:
            request["tools"] = tools
        if previous_response_id:
            request["previous_response_id"] = previous_response_id
        if max_output_tokens is not None:
            request["max_output_tokens"] = max_output_tokens

        started_at = time.perf_counter()
        retries = 5
        document = None
        for attempt in range(retries + 1):
            try:
                response = self.provider.with_timeout(
                    timeout_seconds or self.timeout_seconds
                ).responses.create(**request)
                document = response.model_dump(mode="json")
                break
            except (OpenAIError, OpenAIProviderError, ValueError) as error:
                is_rate_limit = (
                    "429" in str(error)
                    or "Rate limit" in str(error)
                    or "rate_limit_exceeded" in str(error)
                )
                if is_rate_limit and attempt < retries:
                    time.sleep(2.0 * (1.5**attempt))
                    continue
                raise OpenAIResponsesError(
                    f"OpenAI Responses API 호출에 실패했습니다: {error}"
                ) from error

        status = document.get("status")
        if status == "incomplete":
            reason = (document.get("incomplete_details") or {}).get("reason")
            raise OpenAIResponsesError(
                f"OpenAI Responses API 출력이 완료되지 않았습니다: {reason or 'unknown'}"
            )
        if status == "failed":
            error = document.get("error") or {}
            raise OpenAIResponsesError(
                f"OpenAI Responses API 처리에 실패했습니다: {error.get('message') or 'unknown'}"
            )

        content = _output_text(document)
        function_calls = _function_calls(document)
        if not content and not function_calls:
            raise OpenAIResponsesError("OpenAI Responses API가 빈 출력을 반환했습니다")
        return OpenAIResponseResult(
            response_id=str(document.get("id") or ""),
            content=content,
            usage=_usage(document),
            latency_seconds=time.perf_counter() - started_at,
            function_calls=function_calls,
        )

    @staticmethod
    def _prompt_parts(
        messages: list[dict[str, Any]],
    ) -> tuple[str | None, list[dict[str, Any]]]:
        instruction_parts: list[str] = []
        input_items: list[dict[str, Any]] = []
        for message in messages:
            role = message.get("role")
            content = message.get("content", "")
            if role in {"system", "developer"}:
                if isinstance(content, str) and content:
                    instruction_parts.append(content)
                continue
            input_items.append({"role": role, "content": content})
        return "\n\n".join(instruction_parts) or None, input_items

    def complete_structured(
        self,
        model: str,
        messages: list[dict[str, str]],
        schema_name: str,
        json_schema: dict[str, Any],
    ) -> str:
        instructions, input_items = self._prompt_parts(messages)
        return self.create_response(
            model=model,
            instructions=instructions,
            input_items=input_items,
            text_format={
                "type": "json_schema",
                "name": schema_name,
                "strict": True,
                "schema": json_schema,
            },
        ).content

    def complete_vision_structured(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        image_path: Path,
        schema_name: str,
        json_schema: dict[str, Any],
        reasoning_effort: ReasoningEffort,
        max_output_tokens: int,
        timeout_seconds: int,
    ) -> OpenAIResponseResult:
        return self.create_response(
            model=model,
            instructions=system_prompt,
            input_items=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": user_prompt},
                        {
                            "type": "input_image",
                            "image_url": _image_data_url(image_path),
                            "detail": "original",
                        },
                    ],
                }
            ],
            text_format={
                "type": "json_schema",
                "name": schema_name,
                "schema": json_schema,
                "strict": True,
            },
            reasoning_effort=reasoning_effort,
            max_output_tokens=max_output_tokens,
            timeout_seconds=timeout_seconds,
        )

    def close(self) -> None:
        if self._owns_provider:
            self.provider.close()


__all__ = [
    "OpenAIResponseResult",
    "OpenAIResponsesClient",
    "OpenAIResponsesError",
    "ReasoningEffort",
    "project_env_value",
]
