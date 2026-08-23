"""Application-facing embedding port."""

from __future__ import annotations

from typing import Protocol


class EmbeddingEncoder(Protocol):
    def encode(self, queries: list[str]) -> list[list[float]]:
        """Return one numeric vector per query."""
        ...

    def encode_for_model(
        self,
        queries: list[str],
        model_name: str,
    ) -> list[list[float]]:
        """Return vectors using the exact model declared by a stored collection."""
        ...


__all__ = ["EmbeddingEncoder"]
