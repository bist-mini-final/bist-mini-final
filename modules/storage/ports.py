"""Storage capabilities consumed by pipeline storage modules."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Protocol, Sequence

from langchain_core.documents import Document

from backend.domains.data_sources.domain.workbook_profiles import WorkbookProfile
from backend.shared.application.embeddings import EmbeddingEncoder
from backend.shared.application.vector import PgVectorReplacePlan


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


class SourceFileRepositoryPort(Protocol):
    def is_connected(self) -> bool: ...

    def save_source_file(
        self,
        file_id: str,
        file_name: str,
        file_hash: str,
        file_type: str,
        file_size: int,
        storage_path: str,
        **values: Any,
    ) -> None: ...

    def save_sheets(self, file_id: str, sheets_info: list[Dict[str, Any]]) -> None: ...


class WorkbookProfileRepositoryPort(Protocol):
    def save(self, profile: WorkbookProfile, **values: Any) -> WorkbookProfile: ...


__all__ = [
    "IndexCompanyWriterPort",
    "SourceFileRepositoryPort",
    "VectorIngestionPort",
    "WorkbookProfileRepositoryPort",
]
