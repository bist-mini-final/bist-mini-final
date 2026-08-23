"""Embed routed subqueries with each collection's exact embedding contract."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from pydantic import Field

from backend.providers.openai_pricing import calculate_openai_cost
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
from modules.query.decomposer import SubqueryItem
from modules.query.llm_query_router import RetrievalPlanDTO
from modules.storage.pgvector_data_scope import DataScopeDTO


class EmbedderInputDTO(ModuleInputDTO):
    retrieval_plan: RetrievalPlanDTO


class EmbedderConfigDTO(ModuleConfigDTO):
    batch_size: int = Field(
        default=DEFAULT_QUERY_EMBEDDING_BATCH_SIZE,
        ge=1,
        le=2048,
    )


class RoutedEmbeddingDTO(ModuleDTO):
    subquery_index: int = Field(ge=0)
    subquery: SubqueryItem
    collection: DataScopeDTO
    vector: EmbeddingVector


class EmbeddingsDTO(ModuleDTO):
    query_context: QueryContextDTO
    items: List[RoutedEmbeddingDTO] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)


class EmbedderModule(BaseEmbeddingModule):
    """Batches by model/dimension and preserves route-to-vector lineage."""

    definition = ModuleDefinition(
        type="embedder",
        label="Query Embedder",
        category="Logic",
        description=(
            "Router가 선택한 collection의 모델·차원별로 서브쿼리를 묶어 "
            "중복 호출 없이 임베딩합니다."
        ),
        inputs=["retrieval_plan"],
        outputs=["query_embeddings"],
        config_fields=["batch_size"],
        raw_output=True,
        version="10",
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
        plan = input_data.retrieval_plan
        contracts: Dict[Tuple[str, int], List[Tuple[int, SubqueryItem, DataScopeDTO]]] = (
            defaultdict(list)
        )
        for route in plan.routes:
            for collection in route.collections:
                contracts[(collection.model, collection.dimension)].append(
                    (route.subquery_index, route.subquery, collection)
                )

        routed_embeddings: List[Dict[str, Any]] = []
        total_tokens = 0
        total_cost_usd = 0.0
        used_models: List[str] = []
        for (model_name, dimension), routed_items in contracts.items():
            texts = [
                item.text or item.to_serialized_query()
                for _, item, _ in routed_items
            ]
            unique_texts = list(dict.fromkeys(texts))
            vectors = self.encode_texts(
                unique_texts,
                model_name=model_name,
                expected_dimension=dimension,
                batch_size=cfg.batch_size,
                report_progress=False,
            )
            vectors_by_text = dict(zip(unique_texts, vectors, strict=True))
            group_tokens = self.last_total_tokens
            total_tokens += group_tokens
            total_cost_usd += calculate_openai_cost(model_name, group_tokens)
            used_models.append(model_name)
            for (subquery_index, subquery, collection), text in zip(
                routed_items, texts, strict=True
            ):
                routed_embeddings.append(
                    RoutedEmbeddingDTO(
                        subquery_index=subquery_index,
                        subquery=subquery,
                        collection=collection,
                        vector=vectors_by_text[text],
                    ).model_dump(mode="json")
                )

        routed_embeddings.sort(
            key=lambda item: (item["subquery_index"], item["collection"]["index_id"])
        )
        return {
            "query_context": plan.query_context.model_dump(mode="json"),
            "items": routed_embeddings,
            "metrics": {
                "kind": "routed_embeddings",
                "models": list(dict.fromkeys(used_models)),
                "total_tokens": total_tokens,
                "estimated_cost_usd": round(total_cost_usd, 8),
            },
        }


__all__ = [
    "EmbedderConfigDTO",
    "EmbedderInputDTO",
    "EmbedderModule",
    "EmbeddingVector",
    "EmbeddingsDTO",
    "RoutedEmbeddingDTO",
]
