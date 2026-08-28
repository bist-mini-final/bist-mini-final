"""OpenAI embedding gateway using the shared official SDK client."""

from __future__ import annotations

import asyncio
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Sequence

import httpx
from langchain_core.embeddings import Embeddings
from openai import OpenAIError

from backend.providers.openai_provider import OpenAIProvider, OpenAIProviderError
from modules.common.base_module import ModuleExecutionError


def _l2_normalize(vector: List[float]) -> List[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


class OpenAIEmbeddingEncoder(Embeddings):
    """Encode text through the same process-owned SDK client as Responses."""

    def __init__(
        self,
        model_name: str = "text-embedding-3-small",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout_seconds: float = 60,
        http_client: Optional[httpx.Client] = None,
        *,
        provider: OpenAIProvider | None = None,
    ) -> None:
        self.model_name = model_name
        self.last_usage: Dict[str, int] = {}
        self._owns_provider = provider is None
        self.provider = provider or OpenAIProvider(
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            http_client=http_client,
        )

    def _fetch_batch(
        self,
        batch_index: int,
        batch_items: Sequence[str],
        model_name: str,
    ) -> tuple[int, List[List[float]], int, int]:
        try:
            response = self.provider.client.embeddings.create(
                model=model_name,
                input=list(batch_items),
            )
        except (OpenAIError, OpenAIProviderError, ValueError) as error:
            raise ModuleExecutionError(
                f"OpenAI Embeddings API 호출에 실패했습니다: {error}"
            ) from error

        items_by_index: Dict[int, List[float]] = {}
        for item in response.data:
            item_index = item.index
            if (
                not isinstance(item_index, int)
                or isinstance(item_index, bool)
                or item_index in items_by_index
            ):
                raise ModuleExecutionError(
                    "OpenAI Embeddings API 응답 인덱스가 올바르지 않습니다"
                )
            items_by_index[item_index] = list(item.embedding)
        expected_indices = set(range(len(batch_items)))
        if set(items_by_index) != expected_indices:
            raise ModuleExecutionError(
                "OpenAI Embeddings API 응답 인덱스가 요청 범위와 일치하지 않습니다"
            )
        usage = response.usage
        return (
            batch_index,
            [items_by_index[index] for index in range(len(batch_items))],
            int(usage.prompt_tokens or 0),
            int(usage.total_tokens or 0),
        )

    def encode_for_model(
        self,
        queries: List[str],
        model_name: str,
        batch_size: int = 2048,
    ) -> List[List[float]]:
        """Return ordered vectors using the collection's exact model contract."""
        if not queries:
            return []
        effective_batch_size = min(max(1, batch_size), 2048)
        batches = [
            (index, queries[start : start + effective_batch_size])
            for index, start in enumerate(range(0, len(queries), effective_batch_size))
        ]

        results_by_index: Dict[int, List[List[float]]] = {}
        total_prompt_tokens = 0
        total_tokens = 0
        max_workers = min(8, len(batches))
        if max_workers == 1:
            results = [self._fetch_batch(*batches[0], model_name)]
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [
                    executor.submit(self._fetch_batch, index, items, model_name)
                    for index, items in batches
                ]
                results = [future.result() for future in as_completed(futures)]

        for index, vectors, prompt_tokens, batch_total_tokens in results:
            results_by_index[index] = vectors
            total_prompt_tokens += prompt_tokens
            total_tokens += batch_total_tokens

        ordered_vectors = [
            vector
            for index in range(len(batches))
            for vector in results_by_index[index]
        ]
        if len(ordered_vectors) != len(queries):
            raise ModuleExecutionError(
                "생성된 OpenAI 임베딩 개수가 요청과 일치하지 않습니다"
            )
        self.last_usage = {
            "prompt_tokens": total_prompt_tokens,
            "total_tokens": total_tokens,
        }
        return [_l2_normalize(vector) for vector in ordered_vectors]

    def encode(self, queries: List[str], batch_size: int = 2048) -> List[List[float]]:
        """Return vectors using this encoder's default ingestion model."""
        return self.encode_for_model(queries, self.model_name, batch_size)

    async def _fetch_batch_async(
        self,
        batch_index: int,
        batch_items: Sequence[str],
        model_name: str,
    ) -> tuple[int, List[List[float]], int, int]:
        try:
            client = await self.provider.async_client
            response = await client.embeddings.create(
                model=model_name,
                input=list(batch_items),
            )
        except (OpenAIError, OpenAIProviderError, ValueError) as error:
            raise ModuleExecutionError(
                f"OpenAI Embeddings API 호출에 실패했습니다: {error}"
            ) from error
        items_by_index = {item.index: list(item.embedding) for item in response.data}
        expected_indices = set(range(len(batch_items)))
        if set(items_by_index) != expected_indices:
            raise ModuleExecutionError(
                "OpenAI Embeddings API 응답 인덱스가 요청 범위와 일치하지 않습니다"
            )
        return (
            batch_index,
            [items_by_index[index] for index in range(len(batch_items))],
            int(response.usage.prompt_tokens or 0),
            int(response.usage.total_tokens or 0),
        )

    async def encode_for_model_async(
        self,
        queries: List[str],
        model_name: str,
        batch_size: int = 2048,
    ) -> List[List[float]]:
        """Encode bounded batches concurrently through the native async SDK."""
        if not queries:
            return []
        effective_batch_size = min(max(1, batch_size), 2048)
        batches = [
            (index, queries[start : start + effective_batch_size])
            for index, start in enumerate(range(0, len(queries), effective_batch_size))
        ]
        results = await asyncio.gather(
            *(
                self._fetch_batch_async(index, items, model_name)
                for index, items in batches
            )
        )
        results_by_index = {index: vectors for index, vectors, _, _ in results}
        self.last_usage = {
            "prompt_tokens": sum(item[2] for item in results),
            "total_tokens": sum(item[3] for item in results),
        }
        ordered_vectors = [
            vector
            for index in range(len(batches))
            for vector in results_by_index[index]
        ]
        return [_l2_normalize(vector) for vector in ordered_vectors]

    async def encode_async(
        self,
        queries: List[str],
        batch_size: int = 2048,
    ) -> List[List[float]]:
        return await self.encode_for_model_async(queries, self.model_name, batch_size)

    def close(self) -> None:
        if self._owns_provider:
            self.provider.close()

    async def aclose(self) -> None:
        if self._owns_provider:
            await self.provider.aclose()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self.encode(texts)

    def embed_query(self, text: str) -> List[float]:
        vectors = self.encode([text])
        if not vectors:
            raise ValueError(f"Failed to embed query with model {self.model_name}")
        return vectors[0]

    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        return await self.encode_async(texts)

    async def aembed_query(self, text: str) -> List[float]:
        vectors = await self.encode_async([text])
        if not vectors:
            raise ValueError(f"Failed to embed query with model {self.model_name}")
        return vectors[0]


__all__ = ["OpenAIEmbeddingEncoder"]
