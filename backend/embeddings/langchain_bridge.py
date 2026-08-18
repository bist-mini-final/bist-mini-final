"""Bridge between internal EmbeddingEncoder and LangChain Embeddings interface."""

from __future__ import annotations

from typing import List, Optional

from langchain_core.embeddings import Embeddings

from .factory import EmbeddingEncoder, get_embedding_encoder


class LangChainEmbeddingAdapter(Embeddings):
    """Wraps any internal EmbeddingEncoder to conform to LangChain's Embeddings interface."""

    def __init__(
        self,
        model_name: str = "text-embedding-3-large",
        encoder: Optional[EmbeddingEncoder] = None,
    ) -> None:
        self.model_name = model_name
        self.encoder = encoder or get_embedding_encoder(model_name)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed search document texts."""
        if not texts:
            return []
        return self.encoder.encode(texts)

    def embed_query(self, text: str) -> List[float]:
        """Embed a single query text."""
        vectors = self.encoder.encode([text])
        if not vectors:
            raise ValueError(f"Failed to embed query with model {self.model_name}")
        return vectors[0]
