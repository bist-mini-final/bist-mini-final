"""질문과 사전 정의된 쿼리 뱅크 예제 간의 임베딩 코사인 유사도를 계산하여 대상 시트를 라우팅하는 모듈.

질문 임베딩을 생성한 후 카탈로그 내 과거 질문 예시들과의 KNN 코사인 유사도를 측정하고,
설정된 임계값(threshold)과 보팅 마진(vote_margin)을 기반으로 대상 재무제표 시트와 카테고리를 결정합니다.

Example:
    Input DTO (입력 예시):
    ```json
    {
      "query_context": {
        "question_id": "q-001",
        "question_text": "삼성전자 2023년 손익계산서 보여줘"
      }
    }
    ```

    Output DTO (출력 예시):
    ```json
    {
      "semantic_match": {
        "matched": true,
        "target": "손익계산서",
        "sheets": ["손익계산서"],
        "company_name": "삼성전자",
        "items": [
          {
            "example_id": "ex-01",
            "question": "삼성전자 손익계산서 조회",
            "target": "손익계산서",
            "sheets": ["손익계산서"],
            "similarity": 0.94
          }
        ],
        "metrics": {
          "kind": "cosine",
          "model": "text-embedding-3-large",
          "latency_seconds": 0.05
        }
      }
    }
    ```
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from functools import lru_cache
import logging
from pathlib import Path
from threading import Lock
import time
from typing import Any, Dict, List, Optional, Sequence

from pydantic import Field

from backend.core.settings import PROJECT_DIR
from backend.providers.embeddings.factory import EmbeddingEncoder, get_embedding_encoder
from backend.providers.llm.cost import calculate_openai_cost
from backend.storage.embedding_artifacts import EmbeddingArtifactStore
from modules.common.base_embedder import (
    BaseModule,
    EmbeddingConfigDTO,
    ModuleDefinition,
    ModuleDTO,
    ModuleExecutionError,
    ModuleInputDTO,
    QueryContextDTO,
)
from modules.common.config import (
    DEFAULT_SEMANTIC_THRESHOLD,
    DEFAULT_SEMANTIC_TOP_K,
    DEFAULT_SEMANTIC_VOTE_MARGIN,
)

logger = logging.getLogger(__name__)

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


# ==============================================================================
# DTOs
# ==============================================================================
class SemanticQueryMatcherInput(ModuleInputDTO):
    query_context: QueryContextDTO


class SemanticQueryMatcherConfig(EmbeddingConfigDTO):
    threshold: float = Field(default=DEFAULT_SEMANTIC_THRESHOLD, ge=0, le=1)
    top_k: int = Field(default=DEFAULT_SEMANTIC_TOP_K, ge=1, le=20)
    vote_margin: float = Field(default=DEFAULT_SEMANTIC_VOTE_MARGIN, ge=0, le=1)


class SemanticMatchItemDTO(ModuleDTO):
    example_id: str
    question: str
    target: str
    sheets: List[str]
    similarity: float


class CompanyScopeItemDTO(ModuleDTO):
    raw_mention: str = Field(description="질문 내 원본 기업/엔티티 언급 (예: '삼전', '비스텔리젼스')")
    canonical_name: str = Field(description="정규화된 기업명 (예: '삼성전자', '비스텔리젼스')")
    matched_score: float = Field(default=1.0, ge=0.0, le=1.0, description="엔티티 매칭 점수")
    target_topics: List[str] = Field(default_factory=list, description="해당 기업에 할당된 질문 키워드/지표")
    suggested_sheets: List[str] = Field(default_factory=list, description="해당 기업/토픽에 매핑되는 대상 시트")


class RouterMetricsDTO(ModuleDTO):
    kind: str
    model: str
    latency_seconds: float = Field(ge=0)
    api_usage: Dict[str, int] = Field(default_factory=dict)
    estimated_cost_usd: float = Field(default=0, ge=0)


def _legacy_router_metrics() -> RouterMetricsDTO:
    """Keep saved workflows and tests created before benchmark telemetry valid."""
    return RouterMetricsDTO(
        kind="unknown",
        model="unknown",
        latency_seconds=0,
    )


class SemanticQueryMatchOutput(ModuleDTO):
    matched: bool
    target: Optional[str] = None
    sheets: List[str] = Field(default_factory=list)
    items: List[SemanticMatchItemDTO] = Field(default_factory=list, description="매칭된 쿼리 뱅크 예제 목록")
    reason: Optional[str] = None
    company_name: Optional[str] = Field(default=None, description="질문 또는 컨텍스트에서 추출된 단일/대표 대상 기업명")
    company_scopes: List[CompanyScopeItemDTO] = Field(default_factory=list, description="질문에서 추출된 기업별 세부 인텐트 스코프 목록")
    query_type: Optional[int] = None
    subqueries: List[str] = Field(default_factory=list)
    metrics: RouterMetricsDTO = Field(default_factory=_legacy_router_metrics)

    @property
    def matches(self) -> List[SemanticMatchItemDTO]:
        return self.items

    @property
    def confidence(self) -> float:
        return self.items[0].similarity if self.items else (1.0 if self.matched else 0.0)


class SemanticQueryMatcherWorkflowOutput(ModuleDTO):
    """Named workflow port wrapper; the retriever receives its inner value."""

    semantic_match: SemanticQueryMatchOutput


class SemanticQueryMatcherModule(BaseModule):
    definition = ModuleDefinition(
        type="semantic_query_matcher",
        label="Semantic Query Matcher",
        category="Logic",
        description="질문이 기존 쿼리 뱅크 예제와 매칭되는지 코사인 유사도로 판정하여 대상 시트를 라우팅합니다.",
        inputs=["query_context"],
        outputs=["semantic_match"],
        config_fields=["threshold", "top_k", "vote_margin", "model", "dimension", "batch_size"],
        version="3",
    )
    input_model = SemanticQueryMatcherInput
    config_model = SemanticQueryMatcherConfig
    output_model = SemanticQueryMatcherWorkflowOutput

    def __init__(
        self,
        matcher: Optional[SemanticQueryMatcher] = None,
        encoder: Optional[EmbeddingEncoder] = None,
        examples: Optional[Sequence[QueryExample]] = None,
    ) -> None:
        super().__init__()
        self.encoder = encoder
        self.examples = examples
        self.matcher = matcher
        self._matchers: Dict[str, SemanticQueryMatcher] = {}

    def _resolved_matcher(self, config: SemanticQueryMatcherConfig) -> SemanticQueryMatcher:
        if self.matcher is not None:
            return self.matcher

        model = config.model
        matcher = self._matchers.get(model)
        if matcher is None:
            encoder = get_embedding_encoder(
                model_name=model,
                override_encoder=self.encoder,
            )
            examples = tuple(self.examples) if self.examples is not None else None
            matcher = SemanticQueryMatcher(
                encoder=encoder,
                examples=examples,
            )
            self._matchers[model] = matcher
        return matcher

    def execute(
        self,
        input_data: SemanticQueryMatcherInput,
        config: Optional[SemanticQueryMatcherConfig] = None,
    ) -> Dict[str, Any]:
        cfg = config or SemanticQueryMatcherConfig()
        matcher = self._resolved_matcher(cfg)
        started = time.perf_counter()
        decision = matcher.route(
            question=input_data.query_context.question_text,
            model=cfg.model,
            threshold=cfg.threshold,
            top_k=cfg.top_k,
            vote_margin=cfg.vote_margin,
        )
        latency = time.perf_counter() - started

        usage = getattr(matcher.encoder, "last_usage", None)
        if not isinstance(usage, dict):
            usage = {}
        self.last_usage = usage or None
        self.last_model = cfg.model

        estimated_cost = (
            calculate_openai_cost(
                model_name=cfg.model,
                prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
                completion_tokens=0,
                cached_tokens=0,
            )
            if usage
            else 0.0
        )

        model_name = getattr(matcher.encoder, "model_name", cfg.model)

        return {
            "semantic_match": {
                "matched": decision.target is not None,
                "target": decision.target,
                "sheets": list(decision.sheets),
                "company_name": decision.company_name,
                "company_scopes": [],
                "items": [
                    {
                        "example_id": match.example_id,
                        "question": match.question,
                        "target": match.target,
                        "sheets": list(match.sheets),
                        "similarity": round(match.similarity, 10),
                    }
                    for match in decision.matches
                ],
                "reason": decision.reason,
                "query_type": decision.query_type,
                "subqueries": list(decision.subqueries),
                "metrics": {
                    "kind": "cosine",
                    "model": model_name,
                    "latency_seconds": round(latency, 3),
                    "api_usage": usage,
                    "estimated_cost_usd": round(estimated_cost, 8),
                },
            }
        }


# Backward compatibility aliases
SemanticQueryMatcherExecution = SemanticQueryMatcherInput

__all__ = [
    "CompanyScopeItemDTO",
    "QueryExample",
    "RouterMetricsDTO",
    "SemanticDecision",
    "SemanticMatch",
    "SemanticMatchItemDTO",
    "SemanticQueryMatchOutput",
    "SemanticQueryMatcher",
    "SemanticQueryMatcherConfig",
    "SemanticQueryMatcherExecution",
    "SemanticQueryMatcherInput",
    "SemanticQueryMatcherModule",
    "SemanticQueryMatcherWorkflowOutput",
    "load_examples",
]
