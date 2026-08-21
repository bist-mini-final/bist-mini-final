from __future__ import annotations

"""Unified embedding module for query embeddings, batch query embeddings, and Excel cell document embeddings."""

import hashlib
import json
import logging
import time
from typing import Annotated, Any, Dict, List, Optional, Union, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.core.cost_tracker import calculate_embedding_cost
from backend.providers.embeddings.factory import EmbeddingEncoder, get_embedding_encoder
from backend.storage.embedding_artifacts import EmbeddingArtifactStore
from modules.common.base_module import (
    BaseModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleDTO,
    ModuleExecutionError,
    ModuleInputDTO,
    ModuleTaskPolicy,
    QueryContextDTO,
)
from modules.common.config import (
    DEFAULT_CELL_EMBEDDING_BATCH_SIZE,
    DEFAULT_EMBEDDING_MODEL,
    EMBEDDING_MODEL_OPTIONS,
)
from modules.query.decomposer import SubqueriesDTO
from modules.structure.cell_text_serializer import CellTextDocumentDTO, CellTextSerializerOutput

logger = logging.getLogger(__name__)


# ==============================================================================
# 1. Query & Subquery Embedder DTOs & Module
# ==============================================================================

class EmbedderInputDTO(ModuleInputDTO):
    """Decomposer output consumed directly or wrapped under query_input."""

    query_input: Optional[SubqueriesDTO] = None
    subqueries: Optional[List[str]] = None
    query_context: Optional[QueryContextDTO] = None

    @model_validator(mode="after")
    def populate_fields(self) -> "EmbedderInputDTO":
        if self.query_input is not None:
            if self.subqueries is None:
                self.subqueries = self.query_input.subqueries
            if self.query_context is None:
                self.query_context = self.query_input.query_context
        return self


class EmbedderConfigDTO(ModuleConfigDTO):
    model: str = Field(
        default=DEFAULT_EMBEDDING_MODEL,
        min_length=1,
        description="서브쿼리 임베딩에 사용할 3072차원 OpenAI 모델 ID",
        json_schema_extra=cast(
            Any,
            {
                "enum": list(EMBEDDING_MODEL_OPTIONS),
                "options": list(EMBEDDING_MODEL_OPTIONS),
            },
        ),
    )


class EmbedderExecutionDTO(EmbedderInputDTO, EmbedderConfigDTO):
    """Execution model for EmbedderModule."""


EmbeddingVector = Annotated[List[float], Field(min_length=1)]


class EmbeddingsDTO(ModuleDTO):
    query_context: QueryContextDTO = Field(
        description="임베딩이 파생된 원본 질문 컨텍스트"
    )
    items: Dict[str, EmbeddingVector] = Field(
        min_length=0,
        description="서브쿼리를 key, L2 정규화 숫자 벡터를 value로 갖는 매핑",
    )


class EmbedderModule(BaseModule):
    """Encodes decomposed subqueries into dense vectors via single-RTT batch calls."""

    definition = ModuleDefinition(
        type="embedder",
        label="Query Embedder",
        category="Logic",
        description="분해된 서브쿼리 목록을 3072차원 고정밀 벡터로 1 RTT 일괄 변환합니다.",
        inputs=["query_input", "input"],
        outputs=["query_embeddings", "output"],
        config_fields=["model"],
        raw_output=True,
        version="8",
    )
    input_model = EmbedderInputDTO
    config_model = EmbedderConfigDTO
    execution_model = EmbedderExecutionDTO
    output_model = EmbeddingsDTO

    def __init__(self, encoder: Optional[EmbeddingEncoder] = None) -> None:
        self.encoder = encoder
        self._encoders: Dict[str, EmbeddingEncoder] = {}

    def _encoder_for(self, model_name: str) -> EmbeddingEncoder:
        return get_embedding_encoder(
            model_name,
            override_encoder=self.encoder,
            cache=self._encoders,
        )

    def execute(
        self,
        input_data: EmbedderInputDTO,
        config: Optional[EmbedderConfigDTO] = None,
    ) -> Dict[str, Any]:
        if config is None and isinstance(input_data, EmbedderExecutionDTO):
            config = input_data
        model_name = config.model if config else DEFAULT_EMBEDDING_MODEL
        
        subqueries = input_data.subqueries or []
        if input_data.query_context:
            query_context_dict = input_data.query_context.model_dump(mode="json")
        else:
            query_context_dict = {"question_id": "unknown", "question_text": ""}

        unique_subqueries = list(
            dict.fromkeys([sq.strip() for sq in subqueries if sq.strip()])
        )
        if not unique_subqueries and input_data.query_context and input_data.query_context.question_text:
            unique_subqueries = [input_data.query_context.question_text.strip()]

        if not unique_subqueries:
            return {
                "query_context": query_context_dict,
                "items": {},
            }

        encoder = self._encoder_for(model_name)
        vectors = encoder.encode(unique_subqueries)
        self.last_usage = getattr(encoder, "last_usage", None)
        self.last_model = model_name

        if len(vectors) != len(unique_subqueries):
            raise ModuleExecutionError(
                "서브쿼리 개수와 생성된 임베딩 개수가 일치하지 않습니다"
            )

        items = {sq: vec for sq, vec in zip(unique_subqueries, vectors)}
        return {
            "query_context": query_context_dict,
            "items": items,
        }


class BatchQueryEmbedderModule(EmbedderModule):
    """Batch Query Embedder alias with type='batch_query_embedder'."""

    definition = ModuleDefinition(
        type="batch_query_embedder",
        label="Batch Query Embedder",
        category="Logic",
        description="분해된 다중 서브쿼리를 단일 HTTP 배치 요청(1 RTT)으로 전달하여 일괄 임베딩을 생성합니다.",
        inputs=["query_input", "input"],
        outputs=["query_embeddings", "output"],
        config_fields=["model"],
        raw_output=True,
        version="2",
    )


# Batch Query DTO aliases
BatchQueryEmbedderInputDTO = EmbedderInputDTO
BatchQueryEmbedderConfigDTO = EmbedderConfigDTO
BatchQueryEmbedderExecutionDTO = EmbedderExecutionDTO


# ==============================================================================
# 2. Excel Cell Text Document Embedder DTOs & Module
# ==============================================================================

class CellTextEmbedderInputDTO(CellTextSerializerOutput):
    """Structured cell documents produced by a serializer."""


class CellTextEmbedderConfigDTO(ModuleConfigDTO):
    model: str = Field(
        default=DEFAULT_EMBEDDING_MODEL,
        min_length=1,
        description="Excel 셀 문서 임베딩에 사용할 OpenAI 3072차원 모델 ID",
        json_schema_extra=cast(
            Any,
            {
                "enum": list(EMBEDDING_MODEL_OPTIONS),
                "options": list(EMBEDDING_MODEL_OPTIONS),
            },
        ),
    )
    batch_size: int = Field(
        default=DEFAULT_CELL_EMBEDDING_BATCH_SIZE,
        ge=1,
        le=2048,
        description="Excel 셀 문서를 한 번에 임베딩할 배치 크기",
    )


class CellTextEmbedderExecutionDTO(
    CellTextEmbedderInputDTO,
    CellTextEmbedderConfigDTO,
):
    """Internal union of document data and embedding settings."""


class EmbeddedCellTextDocumentDTO(CellTextDocumentDTO):
    embedding_index: int = Field(
        ge=0,
        description="외부 임베딩 아티팩트에서 이 셀 문서 벡터의 행 번호",
    )


class CellTextEmbeddingsDTO(ModuleDTO):
    model_config = ConfigDict(extra="forbid")
    file_name: str
    workbook_hash: str
    model: str = Field(description="문서 임베딩에 사용된 모델 ID")
    artifact_id: str = Field(
        pattern=r"^[a-f0-9]{64}$",
        description="float32 문서 벡터 아티팩트의 콘텐츠 주소",
    )
    dimension: int = Field(gt=0, description="각 문서 임베딩 벡터 차원")
    items: List[EmbeddedCellTextDocumentDTO]
    duration_seconds: Optional[float] = None
    total_tokens: Optional[int] = None
    estimated_cost_usd: Optional[float] = None
    estimated_cost_krw: Optional[float] = None
    batch_size: Optional[int] = None


class CellTextEmbedderModule(BaseModule):
    definition = ModuleDefinition(
        type="cell_text_embedder",
        label="Cell Text Embedder",
        category="Logic",
        description="직렬화된 Excel 셀 문서를 배치 임베딩하고 원본 메타데이터와 함께 반환합니다.",
        inputs=["input"],
        outputs=["output"],
        config_fields=["model", "batch_size"],
        raw_output=True,
        version="3",
        task=ModuleTaskPolicy(
            retries=2,
            retry_delay_seconds=5,
            timeout_seconds=3600,
            tags=["embedding"],
            resource_profile="high-memory",
        ),
    )
    input_model = CellTextEmbedderInputDTO
    config_model = CellTextEmbedderConfigDTO
    execution_model = CellTextEmbedderExecutionDTO
    output_model = CellTextEmbeddingsDTO

    def __init__(
        self,
        encoder: Optional[EmbeddingEncoder] = None,
        artifact_store: Optional[EmbeddingArtifactStore] = None,
    ) -> None:
        self.encoder = encoder
        self.artifact_store = artifact_store or EmbeddingArtifactStore()
        self._encoders: Dict[str, EmbeddingEncoder] = {}

    def _encoder_for(self, model_name: str) -> EmbeddingEncoder:
        return get_embedding_encoder(
            model_name,
            override_encoder=self.encoder,
            cache=self._encoders,
        )

    def execute(
        self,
        input_data: CellTextEmbedderInputDTO,
        config: Optional[CellTextEmbedderConfigDTO] = None,
    ) -> Dict[str, Any]:
        """
        Embed cell documents and store their vectors as a content-addressed artifact.
        """
        if config is None and isinstance(input_data, CellTextEmbedderExecutionDTO):
            cfg = input_data
        else:
            cfg = config or CellTextEmbedderConfigDTO()
        encoder = self._encoder_for(cfg.model)
        vectors: List[List[float]] = []
        if not input_data.items:
            raise ModuleExecutionError("임베딩할 Excel 셀 문서가 없습니다")

        start_perf = time.perf_counter()
        total_tokens = 0
        total_items = len(input_data.items)
        total_batches = max(1, (total_items + cfg.batch_size - 1) // cfg.batch_size)
        self.report_progress(
            {
                "phase": "embedding_batches",
                "completed_batches": 0,
                "total_batches": total_batches,
                "completed_items": 0,
                "total_items": total_items,
            }
        )

        for batch_idx, start in enumerate(range(0, total_items, cfg.batch_size), start=1):
            batch = input_data.items[start : start + cfg.batch_size]
            print(f"[CellTextEmbedder] 배치 {batch_idx}/{total_batches} ({len(batch)}개 문서) 임베딩 중...", flush=True)
            logger.info("임베딩 배치 %d/%d 실행 중 (%d개 문서, 모델: %s)...", batch_idx, total_batches, len(batch), cfg.model)
            batch_vectors = encoder.encode([document.text for document in batch])
            if len(batch_vectors) != len(batch):
                raise ModuleExecutionError(
                    "Excel 셀 문서 개수와 생성된 임베딩 개수가 일치하지 않습니다"
                )
            vectors.extend(batch_vectors)

            # Accumulate token usage
            if hasattr(encoder, "last_usage") and getattr(encoder, "last_usage", None):
                usage = getattr(encoder, "last_usage")
                total_tokens += usage.get("total_tokens", 0)
            else:
                # Estimate ~15 tokens per cell text for local models
                total_tokens += sum(max(1, len(doc.text.split()) * 2) for doc in batch)
            self.report_progress(
                {
                    "phase": "embedding_batches",
                    "completed_batches": batch_idx,
                    "total_batches": total_batches,
                    "completed_items": min(start + len(batch), total_items),
                    "total_items": total_items,
                }
            )

        duration_seconds = round(time.perf_counter() - start_perf, 3)
        cost_info = calculate_embedding_cost(cfg.model, total_tokens)

        dimensions = {len(vector) for vector in vectors}
        if len(dimensions) != 1 or not dimensions or 0 in dimensions:
            raise ModuleExecutionError("Excel 셀 문서 임베딩 차원이 일정하지 않습니다")
        dimension = dimensions.pop()
        artifact_payload = json.dumps(
            {
                "workbook_hash": input_data.workbook_hash,
                "model": cfg.model,
                "texts": [document.text for document in input_data.items],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        artifact_id = hashlib.sha256(artifact_payload.encode("utf-8")).hexdigest()
        self.artifact_store.put(artifact_id, vectors)

        return {
            "file_name": input_data.file_name,
            "workbook_hash": input_data.workbook_hash,
            "model": cfg.model,
            "artifact_id": artifact_id,
            "dimension": dimension,
            "duration_seconds": duration_seconds,
            "total_tokens": total_tokens,
            "estimated_cost_usd": cost_info["cost_usd"],
            "estimated_cost_krw": cost_info["cost_krw"],
            "batch_size": cfg.batch_size,
            "items": [
                {
                    **document.model_dump(),
                    "embedding_index": index,
                }
                for index, document in enumerate(input_data.items)
            ],
        }


__all__ = [
    # Query embedder
    "EmbedderInputDTO",
    "EmbedderConfigDTO",
    "EmbedderExecutionDTO",
    "EmbeddingsDTO",
    "EmbedderModule",
    # Batch query embedder alias
    "BatchQueryEmbedderInputDTO",
    "BatchQueryEmbedderConfigDTO",
    "BatchQueryEmbedderExecutionDTO",
    "BatchQueryEmbedderModule",
    # Cell text embedder
    "CellTextEmbedderInputDTO",
    "CellTextEmbedderConfigDTO",
    "CellTextEmbedderExecutionDTO",
    "EmbeddedCellTextDocumentDTO",
    "CellTextEmbeddingsDTO",
    "CellTextEmbedderModule",
]
