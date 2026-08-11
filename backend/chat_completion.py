import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ChatCompletionError(RuntimeError):
    """Raised when the configured chat-completion service cannot respond."""


@dataclass(frozen=True)
class ChatCompletionResult:
    content: str
    usage: Dict[str, int]
    latency_seconds: float


def _project_env_value(name: str) -> Optional[str]:
    value = os.getenv(name)
    if value:
        return value
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.is_file():
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
    ) -> None:
        self.api_key = api_key or _project_env_value("OPENAI_API_KEY")
        configured_base = (
            base_url
            or _project_env_value("OPENAI_BASE_URL")
            or "https://api.openai.com/v1"
        )
        self.endpoint = f"{configured_base.rstrip('/')}/chat/completions"
        self.timeout_seconds = timeout_seconds

    def complete_with_metadata(
        self,
        model: str,
        messages: List[Dict[str, str]],
        response_format: Optional[Dict[str, Any]] = None,
    ) -> ChatCompletionResult:
        if not self.api_key:
            raise ChatCompletionError("OPENAI_API_KEY가 설정되지 않았습니다")
        request_body: Dict[str, Any] = {"model": model, "messages": messages}
        if response_format is not None:
            request_body["response_format"] = response_format
        body = json.dumps(request_body, ensure_ascii=False).encode("utf-8")
        request = Request(
            self.endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        started_at = time.perf_counter()
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                document = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            raise ChatCompletionError(f"LLM API가 HTTP {error.code}를 반환했습니다") from error
        except (URLError, TimeoutError, OSError, ValueError) as error:
            raise ChatCompletionError("LLM API 호출 또는 응답 해석에 실패했습니다") from error
        try:
            content = document["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise ChatCompletionError("LLM API 응답에 message.content가 없습니다") from error
        if not isinstance(content, str) or not content.strip():
            raise ChatCompletionError("LLM API가 빈 응답을 반환했습니다")
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
            content=content.strip(),
            usage=usage,
            latency_seconds=time.perf_counter() - started_at,
        )

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
