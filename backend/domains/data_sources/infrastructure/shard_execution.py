"""Concrete embedding and pgvector execution for one ingestion shard."""

from __future__ import annotations

from typing import Any, cast

from backend.contracts.vector import PgVectorReplacePlan
from backend.domains.data_sources.infrastructure.filesystem.embedding_artifacts import (
    EmbeddingArtifactStore,
)
from backend.domains.data_sources.infrastructure.spreadsheets.langchain_document import (
    lazy_cell_documents,
)
from backend.shared.application.embeddings import EmbeddingEncoder
from modules.common.exceptions import ModuleExecutionError

from .filesystem.shard_artifacts import IngestionShardArtifactStore


class OpenAIEmbeddingShardExecutor:
    def __init__(
        self,
        artifacts: IngestionShardArtifactStore,
        encoder: EmbeddingEncoder,
    ) -> None:
        self._artifacts = artifacts
        self._encoder = encoder

    def execute(self, payload: dict[str, Any]) -> int:
        artifact_id = str(payload["artifact_id"])
        shard_index = int(payload["shard_index"])
        dimension = int(payload["dimension"])
        model_name = str(payload["model"])
        batch_size = int(payload["batch_size"])
        expected_count = int(payload["count"])
        items = self._artifacts.read_manifest(artifact_id, shard_index)
        texts = [str(item.get("text") or "") for item in items]
        if len(texts) != expected_count or any(not text for text in texts):
            raise ModuleExecutionError(
                "embedding shard manifest의 문서 개수가 올바르지 않습니다"
            )

        encoder = cast(Any, self._encoder)
        encode_for_model = getattr(encoder, "encode_for_model", None)
        vectors = cast(
            list[list[float]],
            (
                encode_for_model(texts, model_name, batch_size)
                if callable(encode_for_model)
                else encoder.encode(texts)
            ),
        )
        if len(vectors) != expected_count or any(
            len(vector) != dimension for vector in vectors
        ):
            raise ModuleExecutionError(
                "embedding shard 결과의 개수 또는 차원이 올바르지 않습니다"
            )
        self._artifacts.put_vector_shard(
            artifact_id,
            shard_index,
            vectors,
            dimension=dimension,
        )
        usage = getattr(self._encoder, "last_usage", None)
        return (
            int(usage.get("total_tokens", 0) or 0)
            if isinstance(usage, dict)
            else 0
        )


class PgVectorCopyShardExecutor:
    def __init__(
        self,
        artifacts: IngestionShardArtifactStore,
        embedding_store: EmbeddingArtifactStore,
        vector_store: Any,
    ) -> None:
        self._artifacts = artifacts
        self._embedding_store = embedding_store
        self._vectors = vector_store

    def execute(self, payload: dict[str, Any]) -> None:
        artifact_id = str(payload["artifact_id"])
        shard_index = int(payload["shard_index"])
        start = int(payload["start"])
        stop = int(payload["stop"])
        count = int(payload["count"])
        dimension = int(payload["dimension"])
        metadata = dict(payload["metadata"])
        if stop - start != count:
            raise ModuleExecutionError("vector COPY shard 범위가 올바르지 않습니다")

        items = self._artifacts.read_manifest(artifact_id, shard_index)
        if len(items) != count:
            raise ModuleExecutionError(
                "vector COPY shard manifest 개수가 올바르지 않습니다"
            )
        vectors = self._embedding_store.vector_range_sequence(
            artifact_id,
            start,
            stop,
            int(metadata["document_count"]),
            dimension,
        )
        documents = lazy_cell_documents(
            items=items,
            file_name=str(metadata.get("file_name") or ""),
            workbook_hash=str(metadata.get("workbook_hash") or ""),
            index_id=str(payload["index_id"]),
            company_name=str(metadata.get("company_name") or ""),
        )
        plan = PgVectorReplacePlan(
            index_id=str(payload["index_id"]),
            operation_id=str(payload["operation_id"]),
            staging_name=str(payload["staging_name"]),
            staging_uuid=str(payload["staging_uuid"]),
            dimension=dimension,
            metadata=metadata,
        )
        self._vectors.copy_prepared_collection_shard(
            plan,
            documents=documents,
            vectors=vectors,
            start_index=start,
        )


__all__ = ["OpenAIEmbeddingShardExecutor", "PgVectorCopyShardExecutor"]
