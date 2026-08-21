"""Batch Query Embedder Module for single-RTT multi-subquery embeddings."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, cast

from pydantic import BaseModel, Field

from backend.providers.embeddings.bge import DEFAULT_BGE_MODEL
from backend.providers.embeddings.factory import EmbeddingEncoder, get_embedding_encoder
from modules.common.base_module import (
    ExecutableModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleExecutionError,
    ModuleInputDTO,
)
from modules.common.config import DEFAULT_EMBEDDING_MODEL, EMBEDDING_MODEL_OPTIONS
from modules.embedding.embedder import EmbeddingsDTO
from modules.query.decomposer import SubqueriesDTO

logger = logging.getLogger(__name__)


class BatchQueryEmbedderInputDTO(ModuleInputDTO):
    query_input: SubqueriesDTO = Field(
        description="Thesaurus 또는 Decomposer에서 전달된 서브쿼리 목록"
    )


class BatchQueryEmbedderConfigDTO(ModuleConfigDTO):
    model: str = Field(
        default=DEFAULT_EMBEDDING_MODEL,
        min_length=1,
        description="다중 서브쿼리 임베딩에 사용할 3072차원 임베딩 모델 ID",
        json_schema_extra={
            "enum": EMBEDDING_MODEL_OPTIONS,
            "options": EMBEDDING_MODEL_OPTIONS,
        },
    )


class BatchQueryEmbedderExecutionDTO(
    BatchQueryEmbedderInputDTO, BatchQueryEmbedderConfigDTO
):
    """Internal union of subquery inputs and embedding settings."""


class BatchQueryEmbedderModule(ExecutableModule):
    """Encodes all decomposed subqueries in a single batch HTTP request (1 RTT)."""

    definition = ModuleDefinition(
        type="batch_query_embedder",
        label="Batch Query Embedder",
        category="Logic",
        description="분해된 다중 서브쿼리를 단일 HTTP 배치 요청(1 RTT)으로 전달하여 200ms 내에 일괄 임베딩을 생성합니다.",
        inputs=["query_input"],
        outputs=["query_embeddings"],
        config_fields=["model"],
        raw_output=True,
        version="1",
    )
    input_model = BatchQueryEmbedderInputDTO
    config_model = BatchQueryEmbedderConfigDTO
    execution_model = BatchQueryEmbedderExecutionDTO
    output_model = EmbeddingsDTO

    def __init__(self, encoder: Optional[EmbeddingEncoder] = None) -> None:
        self.encoder = encoder

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        input_data = cast(BatchQueryEmbedderExecutionDTO, payload)
        subqueries = input_data.query_input.subqueries
        query_context_dict = input_data.query_input.query_context.model_dump(mode="json")

        unique_subqueries = list(dict.fromkeys([sq.strip() for sq in subqueries if sq.strip()]))
        if not unique_subqueries:
            # Fallback to original question text
            q_text = input_data.query_input.query_context.question_text.strip()
            unique_subqueries = [q_text] if q_text else []

        if not unique_subqueries:
            return {
                "query_context": query_context_dict,
                "items": {},
            }

        encoder = self.encoder or get_embedding_encoder(input_data.model)
        try:
            # Single-RTT batch encoding
            vectors = encoder.encode(unique_subqueries)
        except Exception as e:
            logger.exception("BatchQueryEmbedder 임베딩 실패: %s", e)
            raise ModuleExecutionError(f"단일 배치 임베딩 실패: {e}") from e

        items = {sq: vec for sq, vec in zip(unique_subqueries, vectors)}

        return {
            "query_context": query_context_dict,
            "items": items,
        }
