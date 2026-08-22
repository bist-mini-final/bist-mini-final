"""Deterministic embedding-based semantic query catalog and KNN matcher."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional, Sequence

from backend.core.settings import PROJECT_DIR
from backend.providers.embeddings.factory import EmbeddingEncoder
from backend.storage.embedding_artifacts import EmbeddingArtifactStore
from modules.common.exceptions import ModuleExecutionError

DEFAULT_CATALOG_PATH = PROJECT_DIR / "data" / "semantic_query_plans.json"


@dataclass(frozen=True)
class QueryExample:
    example_id: str
    question: str
    target: str
    sheets: tuple[str, ...]
    query_type: int | None = None
    subqueries: tuple[str, ...] = ()


@lru_cache(maxsize=4)
def load_examples(path: str = str(DEFAULT_CATALOG_PATH)) -> tuple[QueryExample, ...]:
    """Load valid catalog entries once per file path."""
    catalog_path = Path(path)
    try:
        raw_items = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read semantic query catalog: {catalog_path}") from error

    examples = []
    for raw in raw_items:
        question = str(raw.get("question") or "").strip()
        target = str(raw.get("target") or "").strip()
        if not question or not target:
            continue
        metadata = raw.get("metadata") or {}
        raw_sheets = metadata.get("sheets") or ([metadata.get("sheet")] if metadata.get("sheet") else [])
        sheets = tuple(str(sheet).strip() for sheet in raw_sheets if str(sheet).strip())
        raw_plan = raw.get("decomposition") or {}
        examples.append(
            QueryExample(
                example_id=str(raw.get("id") or ""),
                question=question,
                target=target,
                sheets=sheets,
                query_type=int(metadata["query_type"]) if metadata.get("query_type") else None,
                subqueries=tuple(str(item) for item in raw_plan.get("subqueries", []) if str(item).strip()),
            )
        )
    if not examples:
        raise ValueError(f"Semantic query catalog is empty: {catalog_path}")
    return tuple(examples)


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
    company_name: str | None = None
    query_type: int | None = None
    subqueries: tuple[str, ...] = ()


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ModuleExecutionError("Semantic query vectors have inconsistent dimensions")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)


class SemanticQueryMatcher:
    """Caches catalog embeddings and makes vote-based route decisions."""

    def __init__(
        self,
        encoder: EmbeddingEncoder,
        catalog_path: str | None = None,
        examples: tuple[QueryExample, ...] | None = None,
        artifact_store: EmbeddingArtifactStore | None = None,
    ) -> None:
        self.encoder = encoder
        self.catalog_path = catalog_path
        self.examples = examples
        self.artifact_store = artifact_store or EmbeddingArtifactStore()
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
            identity = json.dumps(
                {
                    "kind": "semantic-routing-catalog",
                    "model": model,
                    "examples": [
                        {
                            "id": item.example_id,
                            "question": item.question,
                            "target": item.target,
                            "sheets": item.sheets,
                        }
                        for item in examples
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            artifact_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
            metadata_path = self.artifact_store.directory / f"{artifact_id}.semantic.json"
            vectors = self._load_artifact(artifact_id, metadata_path, len(examples))
            if vectors is None:
                vectors = self.encoder.encode([example.question for example in examples])
                if not vectors or any(len(vector) != len(vectors[0]) for vector in vectors):
                    raise ModuleExecutionError("Semantic query catalog embeddings have inconsistent dimensions")
                self.artifact_store.put(artifact_id, vectors)
                metadata_path.write_text(
                    json.dumps(
                        {
                            "artifact_id": artifact_id,
                            "model": model,
                            "count": len(vectors),
                            "dimension": len(vectors[0]),
                        },
                        sort_keys=True,
                    ),
                    encoding="utf-8",
                )
            if len(vectors) != len(examples):
                raise ModuleExecutionError("Semantic query catalog embedding count does not match examples")
            self._cache[model] = (examples, vectors)
            return self._cache[model]

    def _load_artifact(self, artifact_id: str, metadata_path: Path, count: int) -> list[list[float]] | None:
        """Return a validated persisted catalog, or signal a one-time rebuild."""
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata.get("artifact_id") != artifact_id or metadata.get("count") != count:
                return None
            dimension = int(metadata["dimension"])
            return self.artifact_store.get(artifact_id, count, dimension)
        except (OSError, ValueError, KeyError, json.JSONDecodeError, ModuleExecutionError):
            return None

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
                for example, vector in zip(examples, vectors, strict=True)
            ),
            key=lambda item: (-item.similarity, item.example_id),
        )[:top_k]
        if not matches:
            return SemanticDecision(None, 0.0, (), (), "No catalog examples are available")
        top = matches[0]
        if top.similarity < threshold:
            return SemanticDecision(
                None,
                top.similarity,
                (),
                tuple(matches),
                f"Top similarity {top.similarity:.3f} is below threshold {threshold:.3f}; use the full index",
            )
        nearby_matches = tuple(
            candidate
            for candidate in matches
            if candidate.similarity >= top.similarity - vote_margin
        )
        votes: Dict[str, int] = {}
        for candidate in nearby_matches:
            votes[candidate.target] = votes.get(candidate.target, 0) + 1
        target = max(votes, key=lambda value: (votes[value], value == top.target))
        target_matches = tuple(
            candidate for candidate in nearby_matches if candidate.target == target
        )
        representative = target_matches[0]
        sheets = tuple(sorted({sheet for match in target_matches for sheet in match.sheets}))
        representative_example = next(
            item for item in examples if item.example_id == representative.example_id
        )
        return SemanticDecision(
            target,
            representative.similarity,
            sheets,
            tuple(matches),
            (
                f"Top similarity {top.similarity:.3f}; selected-plan similarity "
                f"{representative.similarity:.3f}; nearby-example votes {votes}"
            ),
            query_type=representative_example.query_type,
            subqueries=(),
        )


__all__ = [
    "QueryExample",
    "SemanticDecision",
    "SemanticMatch",
    "SemanticQueryMatcher",
    "load_examples",
]
