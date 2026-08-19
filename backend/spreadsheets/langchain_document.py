"""Standardized conversion between spreadsheet cell representations and LangChain Document objects."""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from langchain_core.documents import Document

from ..modules.cell_text_serializer import CellTextDocumentDTO


def cell_items_to_langchain_documents(
    items: Sequence[CellTextDocumentDTO | Dict[str, Any]],
    file_name: str = "",
    workbook_hash: str = "",
    index_id: str = "",
    company_name: str = "",
) -> List[Document]:
    """Convert raw cell DTOs or dicts into standard LangChain Document objects."""
    documents: List[Document] = []
    for idx, doc in enumerate(items):
        if isinstance(doc, CellTextDocumentDTO):
            doc_dict = doc.model_dump()
        else:
            doc_dict = dict(doc)

        text = doc_dict.get("text", "")
        cell_id = doc_dict.get("cell_id", "")
        doc_id = f"{cell_id}#{idx}" if cell_id else None
        metadata = {
            "cell_id": cell_id,
            "sheet_name": doc_dict.get("sheet_name", ""),
            "cell_coord": doc_dict.get("cell_coord") or doc_dict.get("cell_address", ""),
            "row_header": doc_dict.get("row_header", []),
            "column_header": doc_dict.get("column_header", []),
            "cell_value": str(doc_dict.get("cell_value", "")),
            "variant": doc_dict.get("variant", ""),
            "file_name": file_name,
            "workbook_hash": workbook_hash,
            "index_id": index_id,
            "company_name": doc_dict.get("company_name") or company_name,
        }
        documents.append(
            Document(
                page_content=text,
                metadata=metadata,
                id=doc_id,
            )
        )
    return documents


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
