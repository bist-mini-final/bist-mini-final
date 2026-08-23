"""Application-facing embedding port."""

from __future__ import annotations

from typing import Protocol


class EmbeddingEncoder(Protocol):
    def encode(self, queries: list[str]) -> list[list[float]]:
        """Return one numeric vector per query."""
        ...


__all__ = ["EmbeddingEncoder"]
