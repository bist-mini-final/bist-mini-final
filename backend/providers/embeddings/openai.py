"""Compatibility import for :mod:`backend.platform.openai.embeddings`."""

from backend.platform.openai.embeddings import (
    OpenAIEmbeddingEncoder,
    OpenAIEmbeddingError,
)

__all__ = ["OpenAIEmbeddingEncoder", "OpenAIEmbeddingError"]
