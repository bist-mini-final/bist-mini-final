import math
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from langchain_core.embeddings import Embeddings

from modules.common.base_module import ModuleExecutionError


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


class OpenAIEmbeddingEncoder(Embeddings):
    """Embedding encoder calling OpenAI-compatible embeddings REST API and implementing LangChain Embeddings."""

    def __init__(
        self,
        model_name: str = "text-embedding-3-small",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout_seconds: float = 60,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        """
        Initialize an OpenAI-compatible embedding encoder.
        
        Parameters:
            model_name (str): Embedding model to use.
            api_key (Optional[str]): API key; project configuration is used when omitted.
            base_url (Optional[str]): API base URL; project configuration or the default OpenAI URL is used when omitted.
            timeout_seconds (float): Request timeout in seconds.
        """
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
        self._owns_http_client = http_client is None
        self.http_client = http_client or httpx.Client(
            timeout=httpx.Timeout(timeout_seconds),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    def encode(self, queries: List[str], batch_size: int = 2048) -> List[List[float]]:
        """
        Encode texts into L2-normalized embedding vectors.
        
        Parameters:
            queries (List[str]): Texts to encode.
            batch_size (int): Requested number of texts per API batch, capped at 2,048.
        
        Returns:
            List[List[float]]: Normalized embedding vectors in the same order as the input texts.
        
        Raises:
            ModuleExecutionError: If the API key is missing, an API request fails, the response is invalid, or the number of returned embeddings differs from the number of queries.
        """
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
            """
            Fetches embeddings for a single batch of texts from the OpenAI-compatible API.
            
            Parameters:
            	batch_tuple (tuple): A batch index and the texts to embed.
            
            Returns:
            	tuple: The batch index, embeddings ordered by input position, prompt token count, and total token count.
            
            Raises:
            	ModuleExecutionError: If the request fails after retries or the response has an invalid format.
            """
            b_idx, batch_items = batch_tuple
            request_body: Dict[str, Any] = {
                "model": self.model_name,
                "input": batch_items,
            }
            document = None
            retries = 4
            for attempt in range(retries):
                try:
                    response = self.http_client.post(
                        self.endpoint,
                        json=request_body,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                    )
                    if response.status_code >= 400:
                        message = ""
                        try:
                            error_doc = response.json()
                            message = str(
                                (error_doc.get("error") or {}).get("message") or ""
                            )
                        except (ValueError, AttributeError):
                            pass
                        detail = f": {message}" if message else ""
                        if (
                            response.status_code in (429, 500, 502, 503, 504)
                            and attempt < retries - 1
                        ):
                            time.sleep(1.5 * (2**attempt))
                            continue
                        raise ModuleExecutionError(
                            "OpenAI Embeddings API가 HTTP "
                            f"{response.status_code}를 반환했습니다{detail}"
                        )
                    document = response.json()
                    break
                except ModuleExecutionError:
                    raise
                except (httpx.HTTPError, ValueError) as error:
                    if attempt < retries - 1:
                        time.sleep(1.5 * (2**attempt))
                        continue
                    raise ModuleExecutionError(f"OpenAI Embeddings API 호출 또는 응답 해석에 실패했습니다: {error}") from error

            if not isinstance(document, dict):
                raise ModuleExecutionError("OpenAI Embeddings API 응답이 비어 있거나 올바르지 않습니다")

            try:
                data_items = document.get("data", [])
                usage_doc = document.get("usage") or {}
                p_tokens = int(usage_doc.get("prompt_tokens") or len(batch_items) * 15)
                t_tokens = int(usage_doc.get("total_tokens") or len(batch_items) * 15)
                items_by_index: Dict[int, Dict[str, Any]] = {}
                for item in data_items:
                    item_index = item["index"]
                    if (
                        not isinstance(item_index, int)
                        or isinstance(item_index, bool)
                        or item_index in items_by_index
                    ):
                        raise ModuleExecutionError(
                            "OpenAI Embeddings API 응답 인덱스가 올바르지 않습니다"
                        )
                    items_by_index[item_index] = item
                expected_indices = set(range(len(batch_items)))
                if set(items_by_index) != expected_indices:
                    raise ModuleExecutionError(
                        "OpenAI Embeddings API 응답 인덱스가 요청 범위와 일치하지 않습니다"
                    )
                batch_vectors = [
                    items_by_index[index]["embedding"]
                    for index in range(len(batch_items))
                ]
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

    def close(self) -> None:
        """Close the owned keep-alive connection pool."""
        if self._owns_http_client:
            self.http_client.close()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """LangChain standard interface for embedding a list of document strings."""
        return self.encode(texts)

    def embed_query(self, text: str) -> List[float]:
        """LangChain standard interface for embedding a single query string."""
        vectors = self.encode([text])
        if not vectors:
            raise ValueError(f"Failed to embed query with model {self.model_name}")
        return vectors[0]
