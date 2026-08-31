"""Shared contracts for catalog-scoped query decomposition and retrieval."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import Field

from modules.common.base_module import (
    DocumentContextDTO,
    ModuleDTO,
    QueryContextDTO,
)
from modules.storage.pgvector_data_scope import DataScopeDTO

UNKNOWN_FIELD = "?"


class SubqueryItem(ModuleDTO):
    """One atomic spreadsheet-cell search intent."""

    company: str = Field(default=UNKNOWN_FIELD)
    sheet: str = Field(default=UNKNOWN_FIELD)
    row_header: str = Field(default=UNKNOWN_FIELD)
    column_header: str = Field(default=UNKNOWN_FIELD)
    cell_value: str = Field(default=UNKNOWN_FIELD)
    text: Optional[str] = None

    def to_serialized_query(self) -> str:
        serialized = " | ".join(
            (
                f"Company: {self.company or UNKNOWN_FIELD}",
                f"Sheet: {self.sheet or UNKNOWN_FIELD}",
                f"Row Header: {self.row_header or UNKNOWN_FIELD}",
                f"Column Header: {self.column_header or UNKNOWN_FIELD}",
                f"Cell Value: {self.cell_value or UNKNOWN_FIELD}",
            )
        )
        self.text = serialized
        return serialized


class RoutedSubqueryDTO(ModuleDTO):
    """One atomic query paired with the exact collections it may search."""

    subquery_index: int = Field(ge=0)
    subquery: SubqueryItem
    collections: List[DataScopeDTO] = Field(min_length=1)
    reason: Optional[str] = None


class RetrievalPlanDTO(ModuleDTO):
    """Canonical downstream contract for catalog-scoped hybrid retrieval."""

    query_context: QueryContextDTO
    routes: List[RoutedSubqueryDTO] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)

    @property
    def selected_index_ids(self) -> List[str]:
        return list(
            dict.fromkeys(scope.index_id for route in self.routes for scope in route.collections)
        )


def document_context_for_plan(plan: RetrievalPlanDTO) -> DocumentContextDTO:
    """Build one deterministic multi-collection lineage projection."""
    collections = list(
        {scope.index_id: scope for route in plan.routes for scope in route.collections}.values()
    )
    if not collections:
        return DocumentContextDTO(
            file_name="no-routed-document",
            workbook_hash="no-routed-workbook",
            index_id=None,
        )
    company_names = list(
        dict.fromkeys(scope.company_name for scope in collections if scope.company_name)
    )
    sheet_names = list(dict.fromkeys(sheet for scope in collections for sheet in scope.sheet_names))
    return DocumentContextDTO(
        file_name=", ".join(scope.file_name for scope in collections),
        workbook_hash=",".join(scope.workbook_hash for scope in collections),
        index_id=",".join(scope.index_id for scope in collections),
        company_name=company_names[0] if len(company_names) == 1 else None,
        sheet_names=sheet_names or None,
    )


__all__ = [
    "RetrievalPlanDTO",
    "RoutedSubqueryDTO",
    "SubqueryItem",
    "UNKNOWN_FIELD",
    "document_context_for_plan",
]
