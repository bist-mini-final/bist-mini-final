from typing import Any, Mapping, Optional, Protocol, Sequence


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
