"""Storage capabilities consumed by pipeline storage modules."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Protocol, Sequence

from langchain_core.documents import Document

from backend.contracts.vector import PgVectorReplacePlan
from backend.providers.embeddings.ports import EmbeddingEncoder


class VectorIngestionPort(Protocol):
    def prepare_collection_replace(
        self,
        *,
        index_id: str,
        operation_id: str,
        model_name: str,
        document_count: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PgVectorReplacePlan: ...

    def put_documents(
        self,
        index_id: str,
        documents: Sequence[Document],
        model_name: str,
        embedding_encoder: Optional[EmbeddingEncoder],
        metadata: Optional[Dict[str, Any]],
        vectors: Optional[Any],
        progress_callback: Optional[Callable[[Dict[str, int]], None]],
    ) -> None: ...


class IndexCompanyWriterPort(Protocol):
    def update_index_company(
        self,
        index_id: str,
        company_name: str,
    ) -> Dict[str, Any]: ...


__all__ = ["IndexCompanyWriterPort", "VectorIngestionPort"]
