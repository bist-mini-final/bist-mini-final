import json
import math
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..modules.base import ModuleExecutionError


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
        self.last_usage: Dict[str, int] = {}

    def encode(self, queries: List[str], batch_size: int = 2048) -> List[List[float]]:
        if not queries:
            return []
        if not self.api_key:
            raise ModuleExecutionError("OPENAI_API_KEY가 설정되지 않았습니다")

        from concurrent.futures import ThreadPoolExecutor, as_completed

        # OpenAI allows up to 2048 inputs per request
        effective_batch_size = min(max(1, batch_size), 2048)
        batches = [
            (idx, queries[i : i + effective_batch_size])
            for idx, i in enumerate(range(0, len(queries), effective_batch_size))
        ]

        def _fetch_batch(batch_tuple):
            b_idx, batch_items = batch_tuple
            request_body: Dict[str, Any] = {
                "model": self.model_name,
                "input": batch_items,
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

            document = None
            retries = 4
            for attempt in range(retries):
                try:
                    with urlopen(request, timeout=self.timeout_seconds) as response:
                        document = json.loads(response.read().decode("utf-8"))
                    break
                except HTTPError as error:
                    message = ""
                    try:
                        error_doc = json.loads(error.read().decode("utf-8"))
                        message = str((error_doc.get("error") or {}).get("message") or "")
                    except (OSError, ValueError, AttributeError):
                        pass
                    detail = f": {message}" if message else ""
                    if error.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                        time.sleep(1.5 * (2 ** attempt))
                        continue
                    raise ModuleExecutionError(
                        f"OpenAI Embeddings API가 HTTP {error.code}를 반환했습니다{detail}"
                    ) from error
                except (URLError, TimeoutError, OSError, ValueError) as error:
                    if attempt < retries - 1:
                        time.sleep(1.5 * (2 ** attempt))
                        continue
                    raise ModuleExecutionError(f"OpenAI Embeddings API 호출 또는 응답 해석에 실패했습니다: {error}") from error

            try:
                data_items = document["data"]
                usage_doc = document.get("usage") or {}
                p_tokens = int(usage_doc.get("prompt_tokens") or len(batch_items) * 15)
                t_tokens = int(usage_doc.get("total_tokens") or len(batch_items) * 15)
                sorted_items = sorted(data_items, key=lambda item: item["index"])
                batch_vectors = [item["embedding"] for item in sorted_items]
                return b_idx, batch_vectors, p_tokens, t_tokens
            except (KeyError, IndexError, TypeError) as error:
                raise ModuleExecutionError("OpenAI Embeddings API 응답 포맷이 올바르지 않습니다") from error

        # Run batch requests with concurrency (up to 8 parallel workers)
        max_workers = min(8, len(batches))
        results_by_idx: Dict[int, List[List[float]]] = {}
        total_prompt_tokens = 0
        total_tokens = 0

        if max_workers <= 1:
            for b in batches:
                idx, b_vecs, p_tok, t_tok = _fetch_batch(b)
                results_by_idx[idx] = b_vecs
                total_prompt_tokens += p_tok
                total_tokens += t_tok
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = [pool.submit(_fetch_batch, b) for b in batches]
                for fut in as_completed(futures):
                    idx, b_vecs, p_tok, t_tok = fut.result()
                    results_by_idx[idx] = b_vecs
                    total_prompt_tokens += p_tok
                    total_tokens += t_tok

        # Reconstruct ordered vectors
        all_vectors: List[List[float]] = []
        for i in range(len(batches)):
            all_vectors.extend(results_by_idx[i])

        self.last_usage = {
            "prompt_tokens": total_prompt_tokens,
            "total_tokens": total_tokens,
        }

        if len(all_vectors) != len(queries):
            raise ModuleExecutionError("생성된 OpenAI 임베딩 개수가 요청과 일치하지 않습니다")

        return [_l2_normalize(vec) for vec in all_vectors]
