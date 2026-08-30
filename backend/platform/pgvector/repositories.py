"""Narrow pgvector repositories presented to pipeline modules.

``PgVectorStore`` remains the SQL gateway during migration, but no pipeline
module receives that god object. Each module is wired to the smallest storage
capability it needs, which permits the SQL implementation to be extracted
without changing module contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, cast

from langchain_core.documents import Document

from backend.contracts.vector import PgVectorReplacePlan
from backend.providers.embeddings.ports import EmbeddingEncoder
from backend.storage.pgvector_store import PgVectorStore


class PgVectorCatalogRepository:
    def __init__(self, store: PgVectorStore) -> None:
        self._store = store

    def update_index_company(
        self,
        index_id: str,
        company_name: str,
    ) -> Dict[str, Any]:
        return self._store.update_index_company(index_id, company_name)


class PgVectorIngestionRepository:
    def __init__(self, store: PgVectorStore) -> None:
        self._store = store

    def prepare_collection_replace(
        self,
        *,
        index_id: str,
        operation_id: str,
        model_name: str,
        document_count: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PgVectorReplacePlan:
        return self._store.prepare_collection_replace(
            index_id=index_id,
            operation_id=operation_id,
            model_name=model_name,
            document_count=document_count,
            metadata=metadata,
        )

    def put_documents(
        self,
        index_id: str,
        documents: Sequence[Document],
        model_name: str,
        embedding_encoder: Optional[EmbeddingEncoder],
        metadata: Optional[Dict[str, Any]],
        vectors: Optional[Any],
        progress_callback: Optional[Callable[[Dict[str, int]], None]],
    ) -> None:
        self._store.put_documents(
            index_id=index_id,
            documents=documents,
            model_name=model_name,
            embedding_encoder=embedding_encoder,
            metadata=metadata,
            vectors=vectors,
            progress_callback=progress_callback,
        )


class PgVectorRetrievalRepository:
    def __init__(self, store: PgVectorStore) -> None:
        self._store = store

    def list_data_scopes(self) -> List[Dict[str, Any]]:
        return self._store.list_data_scopes()

    async def list_data_scopes_async(self) -> List[Dict[str, Any]]:
        return await self._store.list_data_scopes_async()

    def similarity_search_by_vector_with_score(
        self,
        collection_name: str,
        embedding: Sequence[float],
        k: int,
        *,
        sheet_names: Optional[Sequence[str]] = None,
        company_name: Optional[str] = None,
    ) -> List[Tuple[Document, float]]:
        return self._store.similarity_search_by_vector_with_score(
            collection_name,
            list(embedding),
            k,
            sheet_names=list(sheet_names) if sheet_names is not None else None,
            company_name=company_name,
        )

    async def similarity_search_by_vector_with_score_async(
        self,
        collection_name: str,
        embedding: Sequence[float],
        k: int,
        *,
        sheet_names: Optional[Sequence[str]] = None,
        company_name: Optional[str] = None,
    ) -> List[Tuple[Document, float]]:
        return await self._store.similarity_search_by_vector_with_score_async(
            collection_name,
            embedding,
            k,
            sheet_names=sheet_names,
            company_name=company_name,
        )

    def keyword_search(
        self,
        *,
        collection_names: Sequence[str],
        query_text: str,
        k: int,
        company_name: Optional[str] = None,
        sheet_name: Optional[str] = None,
    ) -> List[Tuple[str, Dict[str, Any], float, str]]:
        return self._store.keyword_search(
            collection_names=collection_names,
            query_text=query_text,
            k=k,
            company_name=company_name,
            sheet_name=sheet_name,
        )

    async def keyword_search_async(
        self,
        *,
        collection_names: Sequence[str],
        query_text: str,
        k: int,
        company_name: Optional[str] = None,
        sheet_name: Optional[str] = None,
    ) -> List[Tuple[str, Dict[str, Any], float, str]]:
        return await self._store.keyword_search_async(
            collection_names=collection_names,
            query_text=query_text,
            k=k,
            company_name=company_name,
            sheet_name=sheet_name,
        )

    def fetch_rows_cells(
        self,
        *,
        collection_name: str,
        workbook_hash: Optional[str],
        sheet_name: str,
        row_indices: Sequence[int],
        limit_per_row: int = 100,
    ) -> Dict[int, List[Dict[str, Any]]]:
        return self._store.fetch_rows_cells(
            collection_name=collection_name,
            workbook_hash=workbook_hash,
            sheet_name=sheet_name,
            row_indices=list(row_indices),
            limit_per_row=limit_per_row,
        )

    async def fetch_rows_cells_async(
        self,
        *,
        collection_name: str,
        workbook_hash: Optional[str],
        sheet_name: str,
        row_indices: Sequence[int],
        limit_per_row: int = 100,
    ) -> Dict[int, List[Dict[str, Any]]]:
        return await self._store.fetch_rows_cells_async(
            collection_name=collection_name,
            workbook_hash=workbook_hash,
            sheet_name=sheet_name,
            row_indices=row_indices,
            limit_per_row=limit_per_row,
        )

    def fetch_cells_by_metadata(
        self,
        *,
        cell_identifiers: Sequence[str],
        cell_references: Optional[Sequence[Dict[str, Any]]] = None,
        workbook_hash: Optional[str] = None,
        company_name: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        return self._store.fetch_cells_by_metadata(
            cell_identifiers=list(cell_identifiers),
            cell_references=cast(
                Optional[List[Dict[str, Optional[str]]]],
                list(cell_references) if cell_references is not None else None,
            ),
            workbook_hash=workbook_hash,
            company_name=company_name,
            limit=limit,
        )

    async def fetch_cells_by_metadata_async(
        self,
        *,
        cell_identifiers: Sequence[str],
        cell_references: Optional[Sequence[Dict[str, Any]]] = None,
        workbook_hash: Optional[str] = None,
        company_name: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        return await self._store.fetch_cells_by_metadata_async(
            cell_identifiers=cell_identifiers,
            cell_references=cell_references,
            workbook_hash=workbook_hash,
            company_name=company_name,
            limit=limit,
        )


@dataclass(frozen=True, slots=True)
class PgVectorRepositorySet:
    catalog: PgVectorCatalogRepository
    ingestion: PgVectorIngestionRepository
    retrieval: PgVectorRetrievalRepository

    @classmethod
    def create(cls, store: PgVectorStore) -> "PgVectorRepositorySet":
        return cls(
            catalog=PgVectorCatalogRepository(store),
            ingestion=PgVectorIngestionRepository(store),
            retrieval=PgVectorRetrievalRepository(store),
        )


__all__ = [
    "PgVectorCatalogRepository",
    "PgVectorIngestionRepository",
    "PgVectorRepositorySet",
    "PgVectorRetrievalRepository",
]
