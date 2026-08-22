from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import Field

from .models import BiContractModel
from .rag_pipeline_models import (
    RagContext,
    RagContextOutput,
    RagEmbeddings,
    RagLoadedIndex,
    RagQueryContext,
    RagRankedResult,
    RagRetrieval,
    RagSubqueries,
)

if TYPE_CHECKING:
    from backend.runtime.registry import ModuleRegistry


class ExistingRagPipelineSettings(BiContractModel):
    decomposer_model: str = "gpt-5.6-luna"
    decomposer_preset: Literal[
        "luna_decomposer", "rdb_financial", "simple_decomposer"
    ] = "luna_decomposer"
    embedding_model: str = "text-embedding-3-large"
    bm25_k1: float = Field(default=1.5, gt=0)
    bm25_b: float = Field(default=0.75, ge=0, le=1)
    retrieval_top_k: int = Field(default=1000, gt=0)
    rrf_k: int = Field(default=60, gt=0)
    fused_top_k: int = Field(default=100, gt=0)
    ratio_penalty: float = Field(default=0.4, ge=0, le=1)
    adjacent_radius: int = Field(default=3, ge=0)
    max_context_blocks: int = Field(default=500, gt=0)


class ExistingRagPipelineModules:
    def __init__(
        self,
        registry: ModuleRegistry,
        settings: ExistingRagPipelineSettings | None = None,
    ) -> None:
        self._registry = registry
        self._settings = settings or ExistingRagPipelineSettings()
        self._loaded_indexes: dict[str, RagLoadedIndex] = {}

    def decompose(self, query_context: RagQueryContext) -> RagSubqueries:
        output = self._registry.execute(
            "decomposer",
            {"query_context": query_context.model_dump(mode="json")},
            {
                "model": self._settings.decomposer_model,
                "preset": self._settings.decomposer_preset,
            },
        )
        return RagSubqueries.model_validate(output)

    def load_index(self, index_id: str) -> RagLoadedIndex:
        cached = self._loaded_indexes.get(index_id)
        if cached is not None:
            return cached
        output = self._registry.execute(
            "pgvector_collection_loader",
            {"collection_name": index_id, "collection_names": [index_id]},
            {},
        )
        loaded = RagLoadedIndex.model_validate(output)
        self._loaded_indexes[index_id] = loaded
        return loaded

    def embed(self, subqueries: RagSubqueries) -> RagEmbeddings:
        output = self._registry.execute(
            "embedder",
            subqueries.model_dump(mode="json"),
            {"model": self._settings.embedding_model},
        )
        return RagEmbeddings.model_validate(output)

    def retrieve_bm25(
        self,
        subqueries: RagSubqueries,
        loaded: RagLoadedIndex,
    ) -> RagRankedResult:
        output = self._registry.execute(
            "bm25_retriever",
            {
                "query_input": subqueries.model_dump(mode="json"),
                "document_input": loaded.document_output.model_dump(mode="json"),
            },
            {
                "k1": self._settings.bm25_k1,
                "b": self._settings.bm25_b,
                "top_k": self._settings.retrieval_top_k,
            },
        )
        return RagRankedResult.model_validate(output)

    def retrieve_dense(
        self,
        embeddings: RagEmbeddings,
        loaded: RagLoadedIndex,
    ) -> RagRankedResult:
        output = self._registry.execute(
            "pgvector_retriever",
            {
                "query_input": embeddings.model_dump(mode="json"),
                "index_input": loaded.index_output.model_dump(mode="json"),
            },
            {"top_k": self._settings.retrieval_top_k},
        )
        return RagRankedResult.model_validate(output)

    def fuse(
        self,
        bm25: RagRankedResult,
        dense: RagRankedResult,
    ) -> RagRetrieval:
        output = self._registry.execute(
            "rrf_fusion",
            {
                "bm25_result": bm25.model_dump(mode="json"),
                "dense_result": dense.model_dump(mode="json"),
            },
            {
                "rrf_k": self._settings.rrf_k,
                "top_k": self._settings.fused_top_k,
                "ratio_penalty": self._settings.ratio_penalty,
            },
        )
        return RagRetrieval.model_validate(output)

    def expand(
        self,
        retrieval: RagRetrieval,
        loaded: RagLoadedIndex,
    ) -> RagContext:
        output = self._registry.execute(
            "context",
            {
                "retrieval_json": retrieval.model_dump(mode="json"),
                "document_input": loaded.document_output.model_dump(mode="json"),
            },
            {
                "top_k": self._settings.fused_top_k,
                "adjacent_radius": self._settings.adjacent_radius,
                "max_blocks": self._settings.max_context_blocks,
            },
        )
        return RagContextOutput.model_validate(output).context_json
