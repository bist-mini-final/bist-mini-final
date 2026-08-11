from typing import Annotated, Any, Dict, List, Optional, Protocol, cast

from pydantic import BaseModel, Field

from ..bge_encoder import BgeEncoder, DEFAULT_BGE_MODEL
from .base import ExecutableModule, ModuleDefinition, ModuleDTO, ModuleExecutionError
from .decomposer import SubqueriesDTO


class EmbedderInput(SubqueriesDTO):
    model: str = Field(
        default=DEFAULT_BGE_MODEL,
        min_length=1,
        description="서브쿼리 임베딩에 사용할 Hugging Face 모델 ID",
    )


class EmbeddingEncoder(Protocol):
    def encode(self, queries: List[str]) -> List[List[float]]:
        """Return one numeric vector per query."""


EmbeddingVector = Annotated[List[float], Field(min_length=1)]


class EmbeddingsDTO(ModuleDTO):
    question_id: str = Field(description="원본 질문 ID")
    items: Dict[str, EmbeddingVector] = Field(
        min_length=1,
        description="서브쿼리를 key, L2 정규화 숫자 벡터를 value로 갖는 매핑",
    )


class EmbedderModule(ExecutableModule):
    definition = ModuleDefinition(
        type="embedder",
        label="BGE Query Embedder",
        category="Logic",
        description="서브쿼리의 임베딩 실행 메타데이터를 생성합니다.",
        inputs=["input"],
        outputs=["output"],
        config_fields=["model"],
        raw_output=True,
        version="5",
    )
    input_model = EmbedderInput
    output_model = EmbeddingsDTO

    def __init__(self, encoder: Optional[EmbeddingEncoder] = None) -> None:
        self.encoder = encoder
        self._encoders: Dict[str, EmbeddingEncoder] = {}

    def _encoder_for(self, model_name: str) -> EmbeddingEncoder:
        if self.encoder is not None:
            return self.encoder
        if model_name not in self._encoders:
            self._encoders[model_name] = BgeEncoder(model_name)
        return self._encoders[model_name]

    def execute(self, payload: BaseModel) -> Dict[str, Any]:
        input_data = cast(EmbedderInput, payload)
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
            "question_id": input_data.question_id,
            "items": {
                query: vector
                for query, vector in zip(input_data.subqueries, vectors)
            },
        }
