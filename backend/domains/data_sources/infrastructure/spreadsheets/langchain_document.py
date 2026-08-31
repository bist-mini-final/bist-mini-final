"""Standardized conversion between spreadsheet cells and LangChain documents."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Sequence, overload

from langchain_core.documents import Document
from openpyxl.utils.cell import coordinate_to_tuple
from pydantic import BaseModel

if TYPE_CHECKING:
    from modules.structure.cell_text_serializer import CellTextDocumentDTO


def _cell_item_to_document(
    doc: CellTextDocumentDTO | Dict[str, Any],
    index: int,
    *,
    file_name: str,
    workbook_hash: str,
    index_id: str,
    company_name: str,
) -> Document:
    if isinstance(doc, BaseModel):
        doc_dict = doc.model_dump()
    else:
        doc_dict = dict(doc)

    text = doc_dict.get("text", "")
    cell_id = doc_dict.get("cell_id", "")
    prefix = index_id or workbook_hash
    if prefix and cell_id:
        doc_id = f"{prefix}:{cell_id}#{index}"
    elif cell_id:
        doc_id = f"{cell_id}#{index}"
    else:
        doc_id = None
    cell_coord = doc_dict.get("cell_coord") or doc_dict.get("cell_address", "")
    try:
        row_index, col_index = coordinate_to_tuple(str(cell_coord))
    except (TypeError, ValueError):
        row_index, col_index = None, None
    metadata = {
        "cell_id": cell_id,
        "sheet_name": doc_dict.get("sheet_name", ""),
        "cell_coord": cell_coord,
        "row_index": row_index,
        "col_index": col_index,
        "row_header": doc_dict.get("row_header", []),
        "column_header": doc_dict.get("column_header", []),
        "cell_value": str(doc_dict.get("cell_value", "")),
        "variant": doc_dict.get("variant", ""),
        "file_name": file_name,
        "workbook_hash": workbook_hash,
        "index_id": index_id,
        "company_name": doc_dict.get("company_name") or company_name,
    }
    return Document(page_content=text, metadata=metadata, id=doc_id)


class CellDocumentSequence(Sequence[Document]):
    """Lazily convert DTO items to LangChain documents only for the active DB batch."""

    def __init__(
        self,
        items: Sequence[CellTextDocumentDTO | Dict[str, Any]],
        *,
        file_name: str,
        workbook_hash: str,
        index_id: str,
        company_name: str,
    ) -> None:
        self._items = items
        self._kwargs = {
            "file_name": file_name,
            "workbook_hash": workbook_hash,
            "index_id": index_id,
            "company_name": company_name,
        }

    def __len__(self) -> int:
        return len(self._items)

    @overload
    def __getitem__(self, index: int) -> Document: ...

    @overload
    def __getitem__(self, index: slice) -> List[Document]: ...

    def __getitem__(self, index: int | slice) -> Document | List[Document]:
        if isinstance(index, slice):
            start, stop, step = index.indices(len(self))
            return [
                _cell_item_to_document(self._items[position], position, **self._kwargs)
                for position in range(start, stop, step)
            ]
        position = index if index >= 0 else len(self) + index
        if position < 0 or position >= len(self):
            raise IndexError(index)
        return _cell_item_to_document(self._items[position], position, **self._kwargs)


def cell_items_to_langchain_documents(
    items: Sequence[CellTextDocumentDTO | Dict[str, Any]],
    file_name: str = "",
    workbook_hash: str = "",
    index_id: str = "",
    company_name: str = "",
) -> List[Document]:
    """
    Convert cell text records into LangChain `Document` objects with spreadsheet metadata.

    Parameters:
        items (Sequence[CellTextDocumentDTO | Dict[str, Any]]): Cell text DTOs or mappings to convert.
        file_name (str): Name of the source file.
        workbook_hash (str): Hash identifying the source workbook.
        index_id (str): Identifier for the associated index.
        company_name (str): Default company name when a cell record does not provide one.

    Returns:
        List[Document]: Documents containing cell text, identifiers, and spreadsheet metadata.
    """
    return list(
        CellDocumentSequence(
            items,
            file_name=file_name,
            workbook_hash=workbook_hash,
            index_id=index_id,
            company_name=company_name,
        )
    )


def lazy_cell_documents(
    items: Sequence[CellTextDocumentDTO | Dict[str, Any]],
    file_name: str = "",
    workbook_hash: str = "",
    index_id: str = "",
    company_name: str = "",
) -> CellDocumentSequence:
    """Return a bounded-memory document view for batched vector-store insertion."""
    return CellDocumentSequence(
        items,
        file_name=file_name,
        workbook_hash=workbook_hash,
        index_id=index_id,
        company_name=company_name,
    )


def langchain_document_to_cell_item(
    doc: Document,
    score: float = 0.0,
) -> Dict[str, Any]:
    """Convert a retrieved LangChain Document back into a standard cell search hit dict."""
    meta = doc.metadata or {}
    return {
        "score": round(float(score), 4),
        "cell_id": meta.get("cell_id", doc.id or ""),
        "sheet_name": meta.get("sheet_name", ""),
        "cell_coord": meta.get("cell_coord", ""),
        "row_header": meta.get("row_header", []),
        "column_header": meta.get("column_header", []),
        "cell_value": meta.get("cell_value", ""),
        "text": doc.page_content,
        "file_name": meta.get("file_name", ""),
    }
