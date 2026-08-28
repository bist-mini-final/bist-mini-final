"""임베딩 인코더 생명주기 관리 및 배치 임베딩 생성을 전담하는 임베딩 기본 클래스(BaseEmbeddingModule).

LangChain Embeddings 표준 어댑터 기반으로 텍스트 인코딩, 차원 검증, 배치 분할,
진행률 스트리밍 및 API 비용 계산을 일괄 처리합니다.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Annotated, Any, Dict, List, Mapping, Optional, cast

from pydantic import Field

from backend.providers.openai_pricing import calculate_openai_cost

if TYPE_CHECKING:
    pass
from modules.common.base_module import (
    BaseModule,
    DocumentContextDTO,
    EmptyModuleConfigDTO,
    ModuleConfigDTO,
    ModuleConfigPreset,
    ModuleDefinition,
    ModuleDTO,
    ModuleExecutionError,
    ModuleInputDTO,
    ModuleTaskPolicy,
    QueryContextDTO,
    question_id_for,
)
from modules.common.config import (
    DEFAULT_EMBEDDING_DIMENSION,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_EXCHANGE_RATE_KRW_PER_USD,
)

logger = logging.getLogger(__name__)


# ==============================================================================
# 1. Dimension & Cost Helpers
# ==============================================================================


def get_expected_dimension(model_name: Optional[str] = None) -> int:
    """Return the provider's default vector dimension for a known model family."""
    normalized = (model_name or DEFAULT_EMBEDDING_MODEL).lower()
    exact_dimensions = {
        "text-embedding-3-large": 3072,
        "text-embedding-3-small": 1536,
    }
    if normalized in exact_dimensions:
        return exact_dimensions[normalized]
    if "bge-large" in normalized:
        return 1024
    if "bge-base" in normalized:
        return 768
    if "bge-small" in normalized:
        return 384
    return DEFAULT_EMBEDDING_DIMENSION


def calculate_embedding_cost(
    model: str = DEFAULT_EMBEDDING_MODEL,
    total_tokens: int = 0,
    exchange_rate: float = DEFAULT_EXCHANGE_RATE_KRW_PER_USD,
) -> Dict[str, float]:
    """Calculate USD and KRW costs for embedding token usage."""
    cost_usd = calculate_openai_cost(model, total_tokens)
    cost_krw = cost_usd * exchange_rate
    return {
        "cost_usd": round(cost_usd, 6),
        "cost_krw": round(cost_krw, 2),
    }


# ==============================================================================
# 2. Common Embedding Vector & Config DTO
# ==============================================================================

EmbeddingVector = Annotated[
    List[float],
    Field(min_length=1, description="L2 정규화된 부동소수점 임베딩 벡터"),
]


class EmbeddingConfigDTO(ModuleConfigDTO):
    """Common configuration contract for modules that use embedding models."""

    model: str = Field(
        default=DEFAULT_EMBEDDING_MODEL,
        min_length=1,
        description="임베딩 생성에 사용할 모델 ID",
    )
    dimension: Optional[int] = Field(
        default=None,
        ge=1,
        description="임베딩 벡터 차원 (미지정 시 모델 기본 차원 자동 적용)",
    )
    batch_size: int = Field(
        default=128,
        ge=1,
        le=2048,
        description="임베딩 생성 시 인코더에 전달할 배치 크기",
    )

    def get_effective_dimension(self) -> int:
        """Return explicit configured dimension or model's standard dimension."""
        if self.dimension is not None:
            return self.dimension
        return get_expected_dimension(self.model)


# ==============================================================================
# 3. Base Embedding Module
# ==============================================================================


class BaseEmbeddingModule(BaseModule):
    """Base class for all embedding modules managing encoder lifecycle, model resolution,
    batching, token & cost tracking, progress reporting, and strict vector dimension validation.
    """

    def __init__(self, encoder: Any) -> None:
        super().__init__()
        if encoder is None:
            raise ValueError("BaseEmbeddingModule에는 encoder 주입이 필요합니다")
        self.encoder = encoder
        self.last_usage: Optional[Dict[str, Any]] = None
        self.last_model: Optional[str] = None
        self.last_dimension: Optional[int] = None
        self.last_duration_seconds: float = 0.0
        self.last_total_tokens: int = 0

    def resolve_model(self, config: Optional[Any] = None) -> str:
        """Extract and resolve the target model name from a config object or dict."""
        if config is not None:
            if hasattr(config, "model") and getattr(config, "model", None):
                return str(config.model)
            if isinstance(config, Mapping) and config.get("model"):
                return str(config["model"])
        return DEFAULT_EMBEDDING_MODEL

    def resolve_dimension(
        self,
        model_name: Optional[str] = None,
        config: Optional[Any] = None,
    ) -> int:
        """Resolve the expected vector dimension based on config or model registry."""
        if config is not None:
            if hasattr(config, "get_effective_dimension"):
                return int(config.get_effective_dimension())
            if hasattr(config, "dimension") and getattr(config, "dimension", None) is not None:
                return int(config.dimension)
            if isinstance(config, Mapping) and config.get("dimension") is not None:
                return int(config["dimension"])

        effective_model = model_name or self.resolve_model(config)
        return get_expected_dimension(effective_model)

    def resolve_batch_size(
        self,
        config: Optional[Any] = None,
        default: int = 128,
    ) -> int:
        """Resolve the batch size from config or fallback default."""
        if config is not None:
            if hasattr(config, "batch_size") and getattr(config, "batch_size", None) is not None:
                return int(config.batch_size)
            if isinstance(config, Mapping) and config.get("batch_size") is not None:
                return int(config["batch_size"])
        return default

    def _encoder_for(self, model_name: str) -> Any:
        """Return the encoder injected by the process composition root."""
        del model_name
        return self.encoder

    def validate_vectors(
        self,
        vectors: List[List[float]],
        expected_dimension: Optional[int] = None,
        model_name: Optional[str] = None,
    ) -> int:
        """Validate that all generated vectors are non-empty, uniform in length,
        and match the expected dimension for the model. Returns the uniform dimension.
        """
        if not vectors:
            return expected_dimension or DEFAULT_EMBEDDING_DIMENSION

        dimensions = {len(v) for v in vectors}
        if 0 in dimensions or not dimensions:
            raise ModuleExecutionError("생성된 임베딩 벡터에 빈 벡터(0차원)가 포함되어 있습니다.")

        if len(dimensions) > 1:
            raise ModuleExecutionError(
                f"임베딩 벡터들의 차원이 균일하지 않습니다: {sorted(dimensions)}"
            )

        actual_dimension = dimensions.pop()
        target_dimension = expected_dimension or (
            get_expected_dimension(model_name) if model_name else None
        )

        if target_dimension is not None and actual_dimension != target_dimension:
            effective_model = model_name or self.last_model or "unknown"
            raise ModuleExecutionError(
                f"임베딩 차원 불일치: 모델 '{effective_model}'의 예상 차원({target_dimension}D)과 "
                f"실제 생성된 벡터 차원({actual_dimension}D)이 일치하지 않습니다."
            )

        self.last_dimension = actual_dimension
        return actual_dimension

    def encode_batches_streaming(
        self,
        texts: List[str],
        model_name: Optional[str] = None,
        expected_dimension: Optional[int] = None,
        batch_size: Optional[int] = None,
        on_batch_complete: Optional[Any] = None,
        report_progress: bool = True,
    ) -> Any:
        """Encode text strings into dense vectors batch-by-batch, streaming results to an optional
        callback/sink to guarantee O(batch_size) peak memory usage.

        Yields:
            Tuple[start_index, end_index, batch_vectors]
        """
        if not texts:
            self.last_usage = {"total_tokens": 0, "prompt_tokens": 0}
            self.last_model = model_name or DEFAULT_EMBEDDING_MODEL
            self.last_dimension = expected_dimension
            self.last_total_tokens = 0
            self.last_duration_seconds = 0.0
            return

        resolved_model = model_name or DEFAULT_EMBEDDING_MODEL
        target_dimension = expected_dimension or self.resolve_dimension(resolved_model)
        effective_batch_size = max(1, batch_size or 128)
        encoder = self._encoder_for(resolved_model)

        total_items = len(texts)
        total_batches = max(1, (total_items + effective_batch_size - 1) // effective_batch_size)
        total_tokens = 0

        start_perf = time.perf_counter()
        if report_progress:
            self.report_progress(
                {
                    "phase": "embedding_batches",
                    "completed_batches": 0,
                    "total_batches": total_batches,
                    "completed_items": 0,
                    "total_items": total_items,
                }
            )

        for batch_idx, start in enumerate(range(0, total_items, effective_batch_size), start=1):
            end = min(start + effective_batch_size, total_items)
            batch_texts = texts[start:end]
            encode_for_model: Any = getattr(type(encoder), "encode_for_model", None)
            batch_vectors = cast(
                List[List[float]],
                (
                    encoder.encode_for_model(batch_texts, resolved_model)
                    if callable(encode_for_model)
                    else encoder.encode(batch_texts)
                ),
            )

            if len(batch_vectors) != len(batch_texts):
                raise ModuleExecutionError(
                    f"입력 텍스트 개수({len(batch_texts)})와 생성된 임베딩 개수({len(batch_vectors)})가 일치하지 않습니다."
                )

            self.validate_vectors(
                batch_vectors,
                expected_dimension=target_dimension,
                model_name=resolved_model,
            )

            # Accumulate token usage
            usage = getattr(encoder, "last_usage", None)
            if isinstance(usage, dict) and "total_tokens" in usage:
                total_tokens += usage.get("total_tokens", 0)
            else:
                total_tokens += sum(max(1, len(t.split()) * 2) for t in batch_texts)

            if on_batch_complete is not None:
                on_batch_complete(batch_vectors, start, end)

            if report_progress:
                self.report_progress(
                    {
                        "phase": "embedding_batches",
                        "completed_batches": batch_idx,
                        "total_batches": total_batches,
                        "completed_items": end,
                        "total_items": total_items,
                    }
                )

            yield (start, end, batch_vectors)

        duration_seconds = round(time.perf_counter() - start_perf, 3)
        self.last_usage = {"total_tokens": total_tokens, "prompt_tokens": total_tokens}
        self.last_total_tokens = total_tokens
        self.last_duration_seconds = duration_seconds
        self.last_model = resolved_model

    def encode_texts(
        self,
        texts: List[str],
        model_name: Optional[str] = None,
        expected_dimension: Optional[int] = None,
        batch_size: Optional[int] = None,
        report_progress: bool = True,
    ) -> List[List[float]]:
        """Encode a collection of text strings into normalized dense vectors in batches,
        with unified dimension validation, progress reporting, token aggregation, and latency tracking.
        """
        vectors: List[List[float]] = []
        for _, _, batch_vectors in self.encode_batches_streaming(
            texts=texts,
            model_name=model_name,
            expected_dimension=expected_dimension,
            batch_size=batch_size,
            report_progress=report_progress,
        ):
            vectors.extend(batch_vectors)
        return vectors

    async def encode_texts_async(
        self,
        texts: List[str],
        model_name: Optional[str] = None,
        expected_dimension: Optional[int] = None,
        batch_size: Optional[int] = None,
        report_progress: bool = True,
    ) -> List[List[float]]:
        """Encode through a native async encoder while preserving usage contracts."""
        resolved_model = model_name or DEFAULT_EMBEDDING_MODEL
        target_dimension = expected_dimension or self.resolve_dimension(resolved_model)
        effective_batch_size = max(1, batch_size or 128)
        if not texts:
            self.last_usage = {"total_tokens": 0, "prompt_tokens": 0}
            self.last_model = resolved_model
            self.last_dimension = target_dimension
            self.last_total_tokens = 0
            self.last_duration_seconds = 0.0
            return []

        encoder = self._encoder_for(resolved_model)
        started_at = time.perf_counter()
        if report_progress:
            self.report_progress(
                {
                    "phase": "embedding_batches",
                    "completed_batches": 0,
                    "total_batches": 1,
                    "completed_items": 0,
                    "total_items": len(texts),
                }
            )

        encode_for_model_async = getattr(encoder, "encode_for_model_async", None)
        vectors: List[List[float]]
        if callable(encode_for_model_async):
            vectors = cast(
                List[List[float]],
                await cast(Any, encode_for_model_async)(
                    texts,
                    resolved_model,
                    effective_batch_size,
                ),
            )
        else:
            encode_for_model = getattr(encoder, "encode_for_model", None)
            encode = encoder.encode
            vectors = cast(
                List[List[float]],
                await asyncio.to_thread(
                    encode_for_model if callable(encode_for_model) else encode,
                    texts,
                    *(
                        (resolved_model, effective_batch_size)
                        if callable(encode_for_model)
                        else (effective_batch_size,)
                    ),
                ),
            )

        if len(vectors) != len(texts):
            raise ModuleExecutionError(
                f"입력 텍스트 개수({len(texts)})와 생성된 임베딩 개수({len(vectors)})가 일치하지 않습니다."
            )
        self.validate_vectors(
            vectors,
            expected_dimension=target_dimension,
            model_name=resolved_model,
        )
        usage = getattr(encoder, "last_usage", None)
        total_tokens = (
            int(usage.get("total_tokens", 0) or 0)
            if isinstance(usage, dict)
            else sum(max(1, len(text.split()) * 2) for text in texts)
        )
        self.last_usage = {"total_tokens": total_tokens, "prompt_tokens": total_tokens}
        self.last_total_tokens = total_tokens
        self.last_duration_seconds = round(time.perf_counter() - started_at, 3)
        self.last_model = resolved_model
        if report_progress:
            self.report_progress(
                {
                    "phase": "embedding_batches",
                    "completed_batches": 1,
                    "total_batches": 1,
                    "completed_items": len(texts),
                    "total_items": len(texts),
                }
            )
        return vectors

    def execute(
        self,
        input_data: Any,
        config: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Default generic execution for embedding arbitrary text lists."""
        if isinstance(input_data, Mapping):
            texts = input_data.get("texts", [])
        elif hasattr(input_data, "texts"):
            texts = input_data.texts
        elif isinstance(input_data, list):
            texts = input_data
        else:
            texts = []
        model_name = self.resolve_model(config)
        expected_dimension = self.resolve_dimension(model_name=model_name, config=config)
        batch_size = self.resolve_batch_size(config=config)
        vectors = self.encode_texts(
            texts,
            model_name=model_name,
            expected_dimension=expected_dimension,
            batch_size=batch_size,
        )
        return {
            "vectors": vectors,
            "dimension": self.last_dimension or expected_dimension,
            "model": model_name,
            "total_tokens": self.last_total_tokens,
            "duration_seconds": self.last_duration_seconds,
        }


__all__ = [
    "DEFAULT_EMBEDDING_DIMENSION",
    "DEFAULT_EMBEDDING_MODEL",
    "BaseEmbeddingModule",
    "BaseModule",
    "DocumentContextDTO",
    "EmbeddingConfigDTO",
    "EmbeddingVector",
    "EmptyModuleConfigDTO",
    "ModuleConfigDTO",
    "ModuleConfigPreset",
    "ModuleDTO",
    "ModuleDefinition",
    "ModuleExecutionError",
    "ModuleInputDTO",
    "ModuleTaskPolicy",
    "QueryContextDTO",
    "calculate_embedding_cost",
    "get_expected_dimension",
    "question_id_for",
]
