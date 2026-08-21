"""Small Responses API client for structured vision requests."""

from __future__ import annotations

import base64
import json
import mimetypes
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Literal, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from backend.providers.llm.chat_completion import _project_env_value


class OpenAIResponsesVisionError(RuntimeError):
    """Raised when a structured multimodal Responses request cannot finish."""


@dataclass(frozen=True)
class OpenAIResponsesVisionResult:
    content: str
    usage: Dict[str, int]
    latency_seconds: float


def _image_data_url(image_path: Path) -> str:
    mime_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _output_text(document: Dict[str, Any]) -> str:
    direct = document.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    texts = []
    refusals = []
    for output_item in document.get("output") or []:
        if not isinstance(output_item, dict):
            continue
        for content_item in output_item.get("content") or []:
            if not isinstance(content_item, dict):
                continue
            if content_item.get("type") == "output_text":
                value = content_item.get("text")
                if isinstance(value, str) and value.strip():
                    texts.append(value.strip())
            elif content_item.get("type") == "refusal":
                value = content_item.get("refusal")
                if isinstance(value, str) and value.strip():
                    refusals.append(value.strip())
    if texts:
        return "\n".join(texts)
    if refusals:
        raise OpenAIResponsesVisionError("OpenAI API가 이미지 구조 분석 요청을 거절했습니다")
    raise OpenAIResponsesVisionError("OpenAI Responses API 응답에 output_text가 없습니다")


class OpenAIResponsesVisionClient:
    """Send one complete high-detail image using the Responses API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout_seconds: float = 180,
    ) -> None:
        self.api_key = api_key or _project_env_value("OPENAI_API_KEY")
        configured_base = (
            base_url
            or _project_env_value("OPENAI_BASE_URL")
            or "https://api.openai.com/v1"
        )
        self.endpoint = f"{configured_base.rstrip('/')}/responses"
        self.timeout_seconds = timeout_seconds

    def complete_structured(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        image_path: Path,
        schema_name: str,
        json_schema: Dict[str, Any],
        reasoning_effort: Literal["none", "low", "medium", "high"],
        max_output_tokens: int,
        timeout_seconds: int,
    ) -> OpenAIResponsesVisionResult:
        if not self.api_key:
            raise OpenAIResponsesVisionError("OPENAI_API_KEY가 설정되지 않았습니다")

        request_body = {
            "model": model,
            "instructions": system_prompt,
            "input": [
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
            "reasoning": {"effort": reasoning_effort},
            "max_output_tokens": max_output_tokens,
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "schema": json_schema,
                    "strict": True,
                }
            },
        }
        request = Request(
            self.endpoint,
            data=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        started_at = time.perf_counter()
        document = None
        retries = 3
        for attempt in range(retries):
            try:
                with urlopen(
                    request,
                    timeout=float(timeout_seconds or self.timeout_seconds),
                ) as response:
                    document = json.loads(response.read().decode("utf-8"))
                break
            except HTTPError as error:
                message = ""
                try:
                    error_document = json.loads(error.read().decode("utf-8"))
                    message = str((error_document.get("error") or {}).get("message") or "")
                except (OSError, ValueError, AttributeError):
                    pass
                detail = f": {message}" if message else ""
                if error.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                    time.sleep(1.0 * (2 ** attempt))
                    continue
                raise OpenAIResponsesVisionError(
                    f"OpenAI Responses API가 HTTP {error.code}를 반환했습니다{detail}"
                ) from error
            except (URLError, TimeoutError, OSError, ValueError) as error:
                if attempt < retries - 1:
                    time.sleep(1.0 * (2 ** attempt))
                    continue
        if not isinstance(document, dict):
            raise OpenAIResponsesVisionError("OpenAI Responses API 응답이 비어 있거나 올바르지 않습니다")

        if document.get("status") == "incomplete":
            reason = (document.get("incomplete_details") or {}).get("reason")
            raise OpenAIResponsesVisionError(
                f"OpenAI Responses API 출력이 완료되지 않았습니다: {reason or 'unknown'}"
            )
        usage_document = document.get("usage") or {}
        input_details = usage_document.get("input_tokens_details") or {}
        usage = {
            "input_tokens": int(usage_document.get("input_tokens", 0) or 0),
            "output_tokens": int(usage_document.get("output_tokens", 0) or 0),
            "cached_tokens": int(input_details.get("cached_tokens", 0) or 0),
            "total_tokens": int(usage_document.get("total_tokens", 0) or 0),
        }
        return OpenAIResponsesVisionResult(
            content=_output_text(document),
            usage=usage,
            latency_seconds=time.perf_counter() - started_at,
        )
