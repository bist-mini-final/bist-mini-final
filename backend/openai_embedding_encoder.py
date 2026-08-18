import json
import math
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .modules.base import ModuleExecutionError


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


def _l2_normalize(vector: List[float]) -> List[float]:
    norm = math.sqrt(sum(x * x for x in vector))
    if norm == 0:
        return vector
    return [x / norm for x in vector]


class OpenAIEmbeddingEncoder:
    """Embedding encoder calling OpenAI-compatible embeddings REST API."""

    def __init__(
        self,
        model_name: str = "text-embedding-3-small",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout_seconds: float = 60,
    ) -> None:
        self.model_name = model_name
        self.api_key = api_key or _project_env_value("OPENAI_API_KEY")
        configured_base = (
            base_url
            or _project_env_value("OPENAI_BASE_URL")
            or "https://api.openai.com/v1"
        )
        self.endpoint = f"{configured_base.rstrip('/')}/embeddings"
        self.timeout_seconds = timeout_seconds

    def encode(self, queries: List[str]) -> List[List[float]]:
        if not queries:
            return []
        if not self.api_key:
            raise ModuleExecutionError("OPENAI_API_KEY가 설정되지 않았습니다")

        request_body: Dict[str, Any] = {
            "model": self.model_name,
            "input": queries,
        }
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

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                document = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            raise ModuleExecutionError(
                f"OpenAI Embeddings API가 HTTP {error.code}를 반환했습니다"
            ) from error
        except (URLError, TimeoutError, OSError, ValueError) as error:
            raise ModuleExecutionError("OpenAI Embeddings API 호출 또는 응답 해석에 실패했습니다") from error

        try:
            data_items = document["data"]
            # API can return items sorted by index or in arbitrary order
            sorted_items = sorted(data_items, key=lambda item: item["index"])
            vectors = [item["embedding"] for item in sorted_items]
        except (KeyError, IndexError, TypeError) as error:
            raise ModuleExecutionError("OpenAI Embeddings API 응답 포맷이 올바르지 않습니다") from error

        if len(vectors) != len(queries):
            raise ModuleExecutionError("생성된 OpenAI 임베딩 개수가 요청과 일치하지 않습니다")

        # Keep the API-reported usage available to the workflow modules.  This
        # lets a semantic-router experiment count its extra query embedding.
        raw_usage = document.get("usage") or {}
        self.last_usage = {
            "prompt_tokens": int(raw_usage.get("prompt_tokens", 0) or 0),
            "completion_tokens": 0,
            "cached_tokens": 0,
            "total_tokens": int(raw_usage.get("total_tokens", raw_usage.get("prompt_tokens", 0)) or 0),
        }
        return [_l2_normalize(vec) for vec in vectors]
