from typing import Annotated, Any, Dict, List, Optional, cast

from pydantic import BaseModel, Field

from backend.providers.embeddings.bge import DEFAULT_BGE_MODEL
from backend.providers.embeddings.factory import EmbeddingEncoder, get_embedding_encoder
from modules.common.base_module import (
    ExecutableModule,
    ModuleConfigDTO,
    ModuleDefinition,
    ModuleDTO,
    ModuleExecutionError,
    ModuleInputDTO,
    QueryContextDTO,
)
from modules.query.decomposer import SubqueriesDTO

from modules.common.config import DEFAULT_EMBEDDING_MODEL, EMBEDDING_MODEL_OPTIONS


class EmbedderInputDTO(SubqueriesDTO):
    """Decomposer output consumed without module settings mixed in."""


class EmbedderConfigDTO(ModuleConfigDTO):
    model: str = Field(
        default=DEFAULT_EMBEDDING_MODEL,
        min_length=1,
        description="서브쿼리 임베딩에 사용할 OpenAI 3072차원 모델 ID",
        json_schema_extra={
            "enum": EMBEDDING_MODEL_OPTIONS,
            "options": EMBEDDING_MODEL_OPTIONS,
        },
    )


class EmbedderExecutionDTO(EmbedderInputDTO, EmbedderConfigDTO):
    """Internal union of input data and embedding settings."""


EmbeddingVector = Annotated[List[float], Field(min_length=1)]


class EmbeddingsDTO(ModuleDTO):
    query_context: QueryContextDTO = Field(
        description="임베딩이 파생된 원본 질문 컨텍스트"
    )
    items: Dict[str, EmbeddingVector] = Field(
        min_length=1,
        description="서브쿼리를 key, L2 정규화 숫자 벡터를 value로 갖는 매핑",
    )


class EmbedderModule(ExecutableModule):
    definition = ModuleDefinition(
        type="embedder",
        label="Query Embedder",
        category="Logic",
        description="서브쿼리의 임베딩 실행 메타데이터를 생성합니다.",
        inputs=["input"],
        outputs=["output"],
        config_fields=["model"],
        raw_output=True,
        version="7",
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

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        input_data = cast(EmbedderExecutionDTO, payload)
        vectors = self._encoder_for(input_data.model).encode(input_data.subqueries)
        if len(vectors) != len(input_data.subqueries):
            raise ModuleExecutionError(
                "서브쿼리 개수와 생성된 임베딩 개수가 일치하지 않습니다"
            )
        if len(set(input_data.subqueries)) != len(input_data.subqueries):
            raise ModuleExecutionError(
                "서브쿼리-임베딩 매핑의 key로 사용할 중복 서브쿼리가 있습니다"
            )
        return {
            "query_context": input_data.query_context.model_dump(mode="json"),
            "items": {
                query: vector
                for query, vector in zip(input_data.subqueries, vectors)
            },
        }
