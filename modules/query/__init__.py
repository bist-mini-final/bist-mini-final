"""Modules subpackage for query handling, routing, and decomposition."""

from modules.query.contracts import (
    RetrievalPlanDTO,
    RoutedSubqueryDTO,
    SubqueryItem,
    document_context_for_plan,
)
from modules.query.decomposer import (
    DecomposedSubqueriesResponse,
    DecomposerConfigDTO,
    DecomposerInputDTO,
    DecomposerModule,
    ScopedSubquerySelection,
)
from modules.query.query_input import (
    QueryContextOutput,
    QueryInputDTO,
    QueryInputModule,
)

__all__ = [
    "DecomposedSubqueriesResponse",
    "DecomposerConfigDTO",
    "DecomposerInputDTO",
    "DecomposerModule",
    "QueryContextOutput",
    "QueryInputDTO",
    "QueryInputModule",
    "RetrievalPlanDTO",
    "RoutedSubqueryDTO",
    "ScopedSubquerySelection",
    "SubqueryItem",
    "document_context_for_plan",
]
