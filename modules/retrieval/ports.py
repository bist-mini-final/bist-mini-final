"""Storage ports consumed by retrieval pipeline modules."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple

from langchain_core.documents import Document


class DenseVectorSearchPort(Protocol):
    def similarity_search_by_vector_with_score(
        self,
        collection_name: str,
        embedding: Sequence[float],
        k: int,
        *,
        sheet_names: Optional[Sequence[str]] = None,
        company_name: Optional[str] = None,
    ) -> List[Tuple[Document, float]]: ...

    async def similarity_search_by_vector_with_score_async(
        self,
        collection_name: str,
        embedding: Sequence[float],
        k: int,
        *,
        sheet_names: Optional[Sequence[str]] = None,
        company_name: Optional[str] = None,
    ) -> List[Tuple[Document, float]]: ...


class KeywordSearchPort(Protocol):
    def keyword_search(
        self,
        *,
        collection_names: Sequence[str],
        query_text: str,
        k: int,
        company_name: Optional[str] = None,
        sheet_name: Optional[str] = None,
    ) -> List[Tuple[str, Dict[str, Any], float, str]]: ...

    async def keyword_search_async(
        self,
        *,
        collection_names: Sequence[str],
        query_text: str,
        k: int,
        company_name: Optional[str] = None,
        sheet_name: Optional[str] = None,
    ) -> List[Tuple[str, Dict[str, Any], float, str]]: ...


class ContextExpansionStorePort(Protocol):
    def fetch_rows_cells(
        self,
        *,
        collection_name: str,
        workbook_hash: Optional[str],
        sheet_name: str,
        row_indices: Sequence[int],
        limit_per_row: int = 100,
    ) -> Dict[int, List[Dict[str, Any]]]: ...

    async def fetch_rows_cells_async(
        self,
        *,
        collection_name: str,
        workbook_hash: Optional[str],
        sheet_name: str,
        row_indices: Sequence[int],
        limit_per_row: int = 100,
    ) -> Dict[int, List[Dict[str, Any]]]: ...


class DataScopeStorePort(Protocol):
    def list_data_scopes(self) -> List[Dict[str, Any]]: ...

    async def list_data_scopes_async(self) -> List[Dict[str, Any]]: ...


class CellMetadataLookupPort(Protocol):
    def fetch_cells_by_metadata(
        self,
        *,
        cell_identifiers: Sequence[str],
        cell_references: Optional[Sequence[Dict[str, Any]]] = None,
        workbook_hash: Optional[str] = None,
        company_name: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]: ...

    async def fetch_cells_by_metadata_async(
        self,
        *,
        cell_identifiers: Sequence[str],
        cell_references: Optional[Sequence[Dict[str, Any]]] = None,
        workbook_hash: Optional[str] = None,
        company_name: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]: ...


__all__ = [
    "CellMetadataLookupPort",
    "ContextExpansionStorePort",
    "DataScopeStorePort",
    "DenseVectorSearchPort",
    "KeywordSearchPort",
]
