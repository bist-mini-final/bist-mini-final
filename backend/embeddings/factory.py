from typing import Dict, Optional, Protocol

from .bge import BgeEncoder, DEFAULT_BGE_MODEL
from .openai import OpenAIEmbeddingEncoder


class EmbeddingEncoder(Protocol):
    def encode(self, queries: list[str]) -> list[list[float]]:
        """Return one numeric vector per query."""


def get_embedding_encoder(
    model_name: str,
    override_encoder: Optional[EmbeddingEncoder] = None,
    cache: Optional[Dict[str, EmbeddingEncoder]] = None,
) -> EmbeddingEncoder:
    """Return an appropriate EmbeddingEncoder (OpenAI vs BGE) based on model_name."""
    if override_encoder is not None:
        return override_encoder

    if cache is not None and model_name in cache:
        return cache[model_name]

    encoder: EmbeddingEncoder
    if model_name.startswith("text-embedding-"):
        encoder = OpenAIEmbeddingEncoder(model_name=model_name)
    else:
        encoder = BgeEncoder(model_name=model_name)

    if cache is not None:
        cache[model_name] = encoder

    return encoder
