"""BI retrieval boundary ports."""

from typing import Any, Mapping, Optional, Protocol, Sequence

from backend.domains.bi.domain.extraction_models import (
    BiContextCell,
    BiMetricExtractionRequest,
)


class ModuleRegistryPort(Protocol):
    def execute(
        self,
        module_type: str,
        input_payload: dict[str, object],
        config: dict[str, object],
    ) -> object: ...


class RankedCellStorePort(Protocol):
    def get_index_metadata(self, index_id: str) -> Mapping[str, Any]: ...

    def fetch_cells_by_metadata(
        self,
        cell_identifiers: list[str],
        workbook_hash: Optional[str] = None,
        company_name: Optional[str] = None,
        collection_name: Optional[str] = None,
        limit: int = 50,
        cell_references: Optional[list[dict[str, Optional[str]]]] = None,
    ) -> Sequence[Mapping[str, Any]]: ...


class BiMetricEvidencePort(Protocol):
    """Resolve exact, value-bearing evidence for a catalogued BI metric."""

    def retrieve_metric_cells(
        self,
        request: BiMetricExtractionRequest,
        *,
        limit: int,
    ) -> Sequence[BiContextCell]: ...
