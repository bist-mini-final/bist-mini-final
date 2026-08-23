"""Decomposer에서 분해된 각 원자적 서브쿼리들을 고밀도 임베딩 벡터로 변환하는 모듈.

서브쿼리 텍스트 목록을 받아 OpenAI 또는 Dense 임베딩 모델을 통해 L2 정규화된 고밀도 실수 벡터를 생성하고,
후속 벡터 검색기(Retriever)에 전달할 맵핑 딕셔너리(`items: {subquery_text: vector}`)를 구성합니다.

Example:
    Input DTO (입력 예시):
    ```json
    {
      "query_context": {
        "question_id": "q-001",
        "question_text": "삼성전자 영업이익"
      },
      "subqueries": [
        "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: ?"
      ]
    }
    ```

    Output DTO (출력 예시):
    ```json
    {
      "query_context": {
        "question_id": "q-001",
        "question_text": "삼성전자 영업이익"
      },
      "items": {
        "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: ?": [0.0123, -0.0456, 0.0789]
      },
      "model": "text-embedding-3-large",
      "dimension": 3072,
      "metrics": {
        "latency_seconds": 0.08,
        "estimated_cost_usd": 0.00001
      }
    }
    ```
"""

from __future__ import annotations

# ==============================================================================
# 1. Imports
# ==============================================================================
import logging
from typing import Any, Dict, Optional

from pydantic import Field

from modules.common.base_embedder import (
    BaseEmbeddingModule,
    EmbeddingVector,
    ModuleDefinition,
    ModuleDTO,
    ModuleInputDTO,
    QueryContextDTO,
)
from modules.common.base_module import ModuleConfigDTO
from modules.common.config import DEFAULT_QUERY_EMBEDDING_BATCH_SIZE
from modules.query.decomposer import SubqueriesDTO
from modules.storage.pgvector_collection_loader import IndexOutputDTO

logger = logging.getLogger(__name__)


# ==============================================================================
# 2. Query Embedder DTOs
# ==============================================================================
class EmbedderInputDTO(ModuleInputDTO):
    """Subqueries plus the exact target index embedding contract."""

    query_input: SubqueriesDTO
    index_input: IndexOutputDTO


class EmbedderConfigDTO(ModuleConfigDTO):
    """Operational query batching; model and dimension come from the index."""

    batch_size: int = Field(
        default=DEFAULT_QUERY_EMBEDDING_BATCH_SIZE,
        ge=1,
        le=2048,
    )


class EmbeddingsDTO(ModuleDTO):
    query_context: QueryContextDTO = Field(
        description="임베딩이 파생된 원본 질문 컨텍스트"
    )
    items: Dict[str, EmbeddingVector] = Field(
        min_length=0,
        description="서브쿼리를 key, L2 정규화 숫자 벡터를 value로 갖는 매핑",
    )


# ==============================================================================
# 3. Module Implementation
# ==============================================================================
class EmbedderModule(BaseEmbeddingModule):
    """Encodes decomposed subqueries into dense vectors via single-RTT batch calls."""

    definition = ModuleDefinition(
        type="embedder",
        label="Query Embedder",
        category="Logic",
        description="선택한 pgvector 인덱스와 동일한 모델·차원으로 서브쿼리를 1 RTT 일괄 변환합니다.",
        inputs=["query_input", "index_input"],
        outputs=["query_embeddings"],
        config_fields=["batch_size"],
        raw_output=True,
        version="9",
    )
    input_model = EmbedderInputDTO
    config_model = EmbedderConfigDTO
    output_model = EmbeddingsDTO

    def execute(
        self,
        input_data: EmbedderInputDTO,
        config: Optional[EmbedderConfigDTO] = None,
    ) -> Dict[str, Any]:
        cfg = config or EmbedderConfigDTO()
        model_name = input_data.index_input.model
        expected_dimension = input_data.index_input.dimension
        batch_size = cfg.batch_size

        query_context = input_data.query_input.query_context
        query_context_dict = query_context.model_dump(mode="json")
        subqueries = [
            item.text or item.to_serialized_query()
            for item in input_data.query_input.items
        ]

        unique_subqueries = list(
            dict.fromkeys([sq.strip() for sq in subqueries if sq.strip()])
        )
        if not unique_subqueries and query_context.question_text:
            unique_subqueries = [query_context.question_text.strip()]

        if not unique_subqueries:
            return {
                "query_context": query_context_dict,
                "items": {},
            }

        vectors = self.encode_texts(
            unique_subqueries,
            model_name=model_name,
            expected_dimension=expected_dimension,
            batch_size=batch_size,
            report_progress=False,
        )

        items = {sq: vec for sq, vec in zip(unique_subqueries, vectors, strict=True)}
        return {
            "query_context": query_context_dict,
            "items": items,
        }


# ==============================================================================
# 4. Exports
# ==============================================================================
__all__ = [
    "EmbedderConfigDTO",
    "EmbedderInputDTO",
    "EmbedderModule",
    "EmbeddingVector",
    "EmbeddingsDTO",
]
