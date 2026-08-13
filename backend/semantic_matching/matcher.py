"""Deterministic, embedding-based example-query matcher."""

from __future__ import annotations

import math
from dataclasses import dataclass
from threading import Lock
from typing import Dict, Sequence

from .catalog import QueryExample, load_examples
from ..embedding_factory import EmbeddingEncoder
from ..modules.base import ModuleExecutionError


@dataclass(frozen=True)
class SemanticMatch:
    example_id: str
    question: str
    target: str
    sheets: tuple[str, ...]
    similarity: float


@dataclass(frozen=True)
class SemanticDecision:
    target: str | None
    confidence: float
    sheets: tuple[str, ...]
    matches: tuple[SemanticMatch, ...]
    reason: str


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ModuleExecutionError("Semantic query vectors have inconsistent dimensions")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)


class SemanticQueryMatcher:
    """Caches catalog embeddings and makes the same vote-based route decision as rag6."""

    def __init__(
        self,
        encoder: EmbeddingEncoder,
        catalog_path: str | None = None,
        examples: tuple[QueryExample, ...] | None = None,
    ) -> None:
        self.encoder = encoder
        self.catalog_path = catalog_path
        self.examples = examples
        self._cache: Dict[str, tuple[tuple[QueryExample, ...], list[list[float]]]] = {}
        self._lock = Lock()

    def _embedded_catalog(self, model: str) -> tuple[tuple[QueryExample, ...], list[list[float]]]:
        with self._lock:
            cached = self._cache.get(model)
            if cached is not None:
                return cached
            examples = self.examples or (
                load_examples(self.catalog_path) if self.catalog_path else load_examples()
            )
            vectors = self.encoder.encode([example.question for example in examples])
            if len(vectors) != len(examples):
                raise ModuleExecutionError("Semantic query catalog embedding count does not match examples")
            self._cache[model] = (examples, vectors)
            return self._cache[model]

    def route(
        self,
        question: str,
        model: str,
        threshold: float,
        top_k: int,
        vote_margin: float,
    ) -> SemanticDecision:
        examples, vectors = self._embedded_catalog(model)
        query_vectors = self.encoder.encode([question])
        if len(query_vectors) != 1:
            raise ModuleExecutionError("Semantic query embedding did not return one vector")
        matches = sorted(
            (
                SemanticMatch(
                    example_id=example.example_id,
                    question=example.question,
                    target=example.target,
                    sheets=example.sheets,
                    similarity=_cosine(query_vectors[0], vector),
                )
                for example, vector in zip(examples, vectors)
            ),
            key=lambda item: (-item.similarity, item.example_id),
        )[:top_k]
        if not matches:
            return SemanticDecision(None, 0.0, (), (), "No catalog examples are available")
        top = matches[0]
        if top.similarity < threshold:
            return SemanticDecision(
                None, top.similarity, (), tuple(matches),
                f"Top similarity {top.similarity:.3f} is below threshold {threshold:.3f}; use the full index",
            )
        votes: Dict[str, int] = {}
        for candidate in matches:
            if candidate.similarity >= top.similarity - vote_margin:
                votes[candidate.target] = votes.get(candidate.target, 0) + 1
        target = max(votes, key=lambda value: (votes[value], value == top.target))
        sheets = tuple(sorted({sheet for match in matches if match.target == target for sheet in match.sheets}))
        return SemanticDecision(
            target, top.similarity, sheets, tuple(matches),
            f"Top similarity {top.similarity:.3f}; nearby-example votes {votes}",
        )
