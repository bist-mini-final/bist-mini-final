"""Compact PostgreSQL data-scope catalog for automatic query routing."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import Field

from backend.storage.pgvector_store import PgVectorStore
from modules.common.base_module import (
    BaseModule,
    EmptyModuleConfigDTO,
    ModuleDefinition,
    ModuleDTO,
    ModuleExecutionError,
    ModuleInputDTO,
)


class DataScopeDTO(ModuleDTO):
    """One concrete searchable collection and its embedding contract."""

    index_id: str = Field(min_length=1)
    file_name: str = Field(min_length=1)
    workbook_hash: str = Field(min_length=1)
    company_name: str = ""
    sheet_names: List[str] = Field(default_factory=list)
    model: str = Field(min_length=1)
    dimension: int = Field(gt=0)
    document_count: int = Field(default=0, ge=0)


class DataScopeCatalogDTO(ModuleDTO):
    """All compact scopes that the router is allowed to select."""

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
            "LLM Query Router가 서브쿼리별 검색 범위를 자동 선택하게 합니다."
        ),
        inputs=[],
        outputs=["scope_catalog"],
        config_fields=[],
        cacheable=False,
        version="1",
    )
    input_model = PgVectorDataScopeInputDTO
    config_model = EmptyModuleConfigDTO
    output_model = PgVectorDataScopeOutputDTO

    def __init__(self, pgvector_store: PgVectorStore) -> None:
        self.pgvector_store = pgvector_store

    def execute(
        self,
        input_data: PgVectorDataScopeInputDTO,
        config: Optional[EmptyModuleConfigDTO] = None,
    ) -> Dict[str, Any]:
        del input_data, config
        scopes = self.pgvector_store.list_data_scopes()
        if not scopes:
            raise ModuleExecutionError(
                "검색 가능한 PostgreSQL data scope가 없습니다. 먼저 Excel 인덱스를 생성하세요"
            )
        return {
            "scope_catalog": {
                "collections": [
                    DataScopeDTO.model_validate(scope).model_dump(mode="json")
                    for scope in scopes
                ]
            }
        }


__all__ = [
    "DataScopeCatalogDTO",
    "DataScopeDTO",
    "PgVectorDataScopeInputDTO",
    "PgVectorDataScopeModule",
    "PgVectorDataScopeOutputDTO",
]
