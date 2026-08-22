"""OpenAI-compatible chat-completion client used by language modules."""

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx


class ChatCompletionError(RuntimeError):
    """Raised when the configured chat-completion service cannot respond."""


@dataclass(frozen=True)
class ChatCompletionResult:
    content: str
    usage: Dict[str, int]
    latency_seconds: float
    tool_calls: Optional[List[Dict[str, Any]]] = None


def _project_env_value(name: str) -> Optional[str]:
    value = os.getenv(name)
    if value:
        return value
    for parent in Path(__file__).resolve().parents:
        candidate_env = parent / ".env"
        if candidate_env.is_file():
            env_path = candidate_env
            break
    else:
        return None
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, candidate = line.split("=", 1)
        if key.strip() == name:
            return candidate.strip().strip('"').strip("'") or None
    return None


class ChatCompletionClient:
    """Minimal OpenAI-compatible chat-completions client."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout_seconds: float = 30,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        self.api_key = api_key or _project_env_value("OPENAI_API_KEY")
        configured_base = (
            base_url
            or _project_env_value("OPENAI_BASE_URL")
            or "https://api.openai.com/v1"
        )
        self.endpoint = f"{configured_base.rstrip('/')}/chat/completions"
        self.timeout_seconds = timeout_seconds
        self._owns_http_client = http_client is None
        self.http_client = http_client or httpx.Client(
            timeout=httpx.Timeout(timeout_seconds),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
        )

    def complete_with_metadata(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        response_format: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Any] = None,
    ) -> ChatCompletionResult:
        if not self.api_key:
            raise ChatCompletionError("OPENAI_API_KEY가 설정되지 않았습니다")
        request_body: Dict[str, Any] = {"model": model, "messages": messages}
        if response_format is not None:
            request_body["response_format"] = response_format
        if tools is not None:
            request_body["tools"] = tools
        if tool_choice is not None:
            request_body["tool_choice"] = tool_choice
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        started_at = time.perf_counter()
        document = None
        retries = 10
        max_retry_budget_seconds = 60.0
        for attempt in range(retries):
            try:
                response = self.http_client.post(
                    self.endpoint,
                    json=request_body,
                    headers=headers,
                )
                if response.status_code >= 400:
                    message = ""
                    try:
                        error_doc = response.json()
                        message = str((error_doc.get("error") or {}).get("message") or "")
                    except (ValueError, AttributeError):
                        pass
                    detail = f": {message}" if message else ""
                    elapsed = time.perf_counter() - started_at
                    if (
                        response.status_code in (429, 500, 502, 503, 504)
                        and attempt < retries - 1
                        and elapsed < max_retry_budget_seconds
                    ):
                        sleep_time = min(30.0, 1.5 * (1.5**attempt))
                        if response.status_code == 429 and message:
                            try:
                                import re

                                match = re.search(
                                    r"try again in ([0-9]+(?:\.[0-9]+)?)(m?s)",
                                    message,
                                )
                                if match:
                                    value = float(match.group(1))
                                    parsed_delay = (
                                        value / 1000.0
                                        if match.group(2) == "ms"
                                        else value
                                    )
                                    sleep_time = min(30.0, max(0.05, parsed_delay))
                            except (ValueError, TypeError, AttributeError):
                                pass
                        if elapsed + sleep_time > max_retry_budget_seconds:
                            raise ChatCompletionError(
                                f"LLM API가 HTTP {response.status_code}를 반환했습니다 "
                                f"(재시도 예산 초과){detail}"
                            )
                        time.sleep(sleep_time)
                        continue
                    raise ChatCompletionError(
                        f"LLM API가 HTTP {response.status_code}를 반환했습니다{detail}"
                    )
                document = response.json()
                break
            except ChatCompletionError:
                raise
            except (httpx.HTTPError, ValueError) as error:
                elapsed = time.perf_counter() - started_at
                if attempt < retries - 1 and elapsed < max_retry_budget_seconds:
                    sleep_time = min(15.0, 2.0 * (2 ** attempt))
                    if elapsed + sleep_time > max_retry_budget_seconds:
                        raise ChatCompletionError(f"LLM API 호출 재시도 예산 초과: {error}") from error
                    time.sleep(sleep_time)
                    continue
        if not isinstance(document, dict):
            raise ChatCompletionError("LLM API 응답이 비어 있거나 올바르지 않습니다")
        try:
            choice_message = document["choices"][0]["message"]
            content = choice_message.get("content") or ""
            tool_calls = choice_message.get("tool_calls")
        except (KeyError, IndexError, TypeError) as error:
            raise ChatCompletionError("LLM API 응답 메시지 구조가 올바르지 않습니다") from error
        if not (isinstance(content, str) and content.strip()) and not tool_calls:
            raise ChatCompletionError("LLM API가 빈 응답(content 및 tool_calls 없음)을 반환했습니다")
        raw_usage = document.get("usage") or {}
        prompt_details = raw_usage.get("prompt_tokens_details") or {}
        completion_details = raw_usage.get("completion_tokens_details") or {}
        usage = {
            "prompt_tokens": int(raw_usage.get("prompt_tokens", 0) or 0),
            "completion_tokens": int(raw_usage.get("completion_tokens", 0) or 0),
            "cached_tokens": int(prompt_details.get("cached_tokens", 0) or 0),
            "reasoning_tokens": int(
                completion_details.get("reasoning_tokens", 0) or 0
            ),
            "total_tokens": int(raw_usage.get("total_tokens", 0) or 0),
        }
        return ChatCompletionResult(
            content=content.strip() if isinstance(content, str) else "",
            usage=usage,
            latency_seconds=time.perf_counter() - started_at,
            tool_calls=tool_calls,
        )

    def close(self) -> None:
        """Close the owned keep-alive connection pool."""
        if self._owns_http_client:
            self.http_client.close()

    def complete(self, model: str, messages: List[Dict[str, str]]) -> str:
        return self.complete_with_metadata(model, messages).content

    def complete_structured(
        self,
        model: str,
        messages: List[Dict[str, str]],
        schema_name: str,
        json_schema: Dict[str, Any],
    ) -> str:
        """Request strict JSON Schema output from an OpenAI-compatible API."""

        return self.complete_with_metadata(
            model,
            messages,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": json_schema,
                },
            },
        ).content
