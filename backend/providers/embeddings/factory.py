from __future__ import annotations

import threading
from typing import Dict, Optional, Protocol

from .bge import BgeEncoder
from .openai import OpenAIEmbeddingEncoder


class EmbeddingEncoder(Protocol):
    def encode(self, queries: list[str]) -> list[list[float]]:
        """Return one numeric vector per query."""
        ...


_GLOBAL_ENCODER_CACHE: Dict[str, EmbeddingEncoder] = {}
_ENCODER_LOCK = threading.Lock()


def get_embedding_encoder(
    model_name: str,
    override_encoder: Optional[EmbeddingEncoder] = None,
    cache: Optional[Dict[str, EmbeddingEncoder]] = None,
) -> EmbeddingEncoder:
    """Return a thread-safe singleton EmbeddingEncoder based on model_name."""
    if override_encoder is not None:
        return override_encoder

    effective_cache = cache if cache is not None else _GLOBAL_ENCODER_CACHE

    if model_name in effective_cache:
        return effective_cache[model_name]

    with _ENCODER_LOCK:
        if model_name in effective_cache:
            return effective_cache[model_name]

        encoder: EmbeddingEncoder
        if model_name.startswith("text-embedding-"):
            encoder = OpenAIEmbeddingEncoder(model_name=model_name)
        else:
            encoder = BgeEncoder(model_name=model_name)

        effective_cache[model_name] = encoder
        return encoder
