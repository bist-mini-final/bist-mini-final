from typing import Mapping, Protocol, Sequence


class ModuleRegistryPort(Protocol):
    def execute(
        self,
        module_type: str,
        input_payload: dict[str, object],
        config: dict[str, object],
    ) -> object: ...


class RankedCellStorePort(Protocol):
    def fetch_cells_by_metadata(
        self,
        cell_identifiers: list[str],
        workbook_hash: str | None = None,
        collection_name: str | None = None,
        limit: int = 50,
    ) -> Sequence[Mapping[str, object]]: ...
