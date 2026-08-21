from __future__ import annotations

from typing import Optional, Annotated, Any, Dict, List, Union, cast

from pydantic import Field, model_validator

from backend.providers.embeddings.factory import EmbeddingEncoder, get_embedding_encoder
from modules.common.base_module import (
    BaseModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleDTO,
    ModuleExecutionError,
    ModuleInputDTO,
    QueryContextDTO,
)
from modules.common.config import DEFAULT_EMBEDDING_MODEL, EMBEDDING_MODEL_OPTIONS
from modules.query.decomposer import SubqueriesDTO


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


# DTO aliases
BatchQueryEmbedderInputDTO = EmbedderInputDTO
BatchQueryEmbedderConfigDTO = EmbedderConfigDTO
BatchQueryEmbedderExecutionDTO = EmbedderExecutionDTO
