"""Compact PostgreSQL data-scope catalog for automatic query routing."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import Field

from modules.common.base_module import (
    BaseModule,
    EmptyModuleConfigDTO,
    ModuleDefinition,
    ModuleDTO,
    ModuleExecutionError,
    ModuleInputDTO,
)
from modules.retrieval.ports import DataScopeStorePort


class DataScopeDTO(ModuleDTO):
    """One concrete searchable collection and its embedding contract."""

    index_id: str = Field(min_length=1)
    file_name: str = Field(min_length=1)
    workbook_hash: str = Field(min_length=1)
    company_name: str = ""
    ticker: str = ""
    sheet_names: List[str] = Field(default_factory=list)
    model: str = Field(min_length=1)
    dimension: int = Field(gt=0)
    document_count: int = Field(default=0, ge=0)


class DataScopeCatalogDTO(ModuleDTO):
    """All compact scopes that query decomposition is allowed to select."""

    collections: List[DataScopeDTO] = Field(default_factory=list)


class PgVectorDataScopeInputDTO(ModuleInputDTO):
    """The catalog is discovered from PostgreSQL and has no user input."""


class PgVectorDataScopeOutputDTO(ModuleDTO):
    scope_catalog: DataScopeCatalogDTO


class PgVectorDataScopeModule(BaseModule):
    """Loads routing metadata only; vectors and documents stay in PostgreSQL."""

    definition = ModuleDefinition(
        type="pgvector_data_scope",
        label="PostgreSQL Data Scope",
        category="Source",
        description=(
            "DB의 collection·company·sheet·embedding 계약만 읽어 "
            "Query Decomposer가 실제 데이터 범위 안에서 검색 계획을 만들게 합니다."
        ),
        inputs=[],
        outputs=["scope_catalog"],
        config_fields=[],
        cacheable=False,
        version="2",
    )
    input_model = PgVectorDataScopeInputDTO
    config_model = EmptyModuleConfigDTO
    output_model = PgVectorDataScopeOutputDTO

    def __init__(self, pgvector_store: DataScopeStorePort) -> None:
        self.pgvector_store = pgvector_store

    @staticmethod
    def _output(scopes: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not scopes:
            raise ModuleExecutionError(
                "검색 가능한 PostgreSQL data scope가 없습니다. 먼저 Excel 인덱스를 생성하세요"
            )
        return {
            "scope_catalog": {
                "collections": [
                    DataScopeDTO.model_validate(scope).model_dump(mode="json") for scope in scopes
                ]
            }
        }

    def execute(
        self,
        input_data: PgVectorDataScopeInputDTO,
        config: Optional[EmptyModuleConfigDTO] = None,
    ) -> Dict[str, Any]:
        del input_data, config
        scopes = self.pgvector_store.list_data_scopes()
        return self._output(scopes)

    async def execute_async(
        self,
        input_data: PgVectorDataScopeInputDTO,
        config: Optional[EmptyModuleConfigDTO] = None,
    ) -> Dict[str, Any]:
        del input_data, config
        scopes = await self.pgvector_store.list_data_scopes_async()
        return self._output(scopes)


__all__ = [
    "DataScopeCatalogDTO",
    "DataScopeDTO",
    "PgVectorDataScopeInputDTO",
    "PgVectorDataScopeModule",
    "PgVectorDataScopeOutputDTO",
]
