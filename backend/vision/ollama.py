"""Ollama multimodal client for local vision modules."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any, Dict
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class OllamaVisionError(RuntimeError):
    pass


class OllamaVisionClient:
    """Small local-only Ollama vision client with JSON Schema output."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip("/")
        parsed = urlparse(self.base_url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("OLLAMA_BASE_URL은 로컬 HTTP 주소만 사용할 수 있습니다")

    def complete_structured(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        image_path: Path,
        json_schema: Dict[str, Any],
        context_window: int,
        timeout_seconds: int,
    ) -> str:
        image_base64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
        schema_text = json.dumps(json_schema, ensure_ascii=False, separators=(",", ":"))
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"{user_prompt}\n\nRequired JSON Schema:\n{schema_text}",
                    "images": [image_base64],
                },
            ],
            "format": json_schema,
            "stream": False,
            "think": False,
            "keep_alive": "10m",
            "options": {
                "temperature": 0,
                "seed": 0,
                "num_ctx": context_window,
            },
        }
        request = Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            if error.code == 404:
                detail = f"모델이 없습니다. 먼저 `ollama pull {model}`을 실행하세요. {detail}"
            raise OllamaVisionError(f"Ollama 요청 실패 ({error.code}): {detail}") from error
        except URLError as error:
            raise OllamaVisionError(
                "로컬 Ollama에 연결할 수 없습니다. Ollama 앱 또는 `ollama serve`를 실행하세요"
            ) from error
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise OllamaVisionError(f"Ollama 응답을 읽을 수 없습니다: {error}") from error

        content = body.get("message", {}).get("content") if isinstance(body, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise OllamaVisionError("Ollama가 구조화된 응답을 반환하지 않았습니다")
        return content
