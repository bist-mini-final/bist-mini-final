from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from modules.common.base_module import ModuleExecutionError
from modules.storage.pgvector_data_scope import (
    DataScopeCatalogDTO,
    PgVectorDataScopeInputDTO,
    PgVectorDataScopeModule,
)


def test_data_scope_reads_compact_routing_catalog_without_user_selection() -> None:
    store = MagicMock()
    store.list_data_scopes.return_value = [
        {
            "index_id": "idx-financials",
            "file_name": "financials.xlsx",
            "workbook_hash": "hash-1",
            "company_name": "Example Corp",
            "sheet_names": ["Income Statement"],
            "model": "text-embedding-3-small",
            "dimension": 1536,
            "document_count": 120,
        }
    ]
    result = PgVectorDataScopeModule(store).run(PgVectorDataScopeInputDTO())
    store.list_data_scopes_async = AsyncMock(return_value=store.list_data_scopes.return_value)
    async_result = asyncio.run(
        PgVectorDataScopeModule(store).run_async(PgVectorDataScopeInputDTO())
    )
    catalog = DataScopeCatalogDTO.model_validate(result["scope_catalog"])

    assert catalog.collections[0].index_id == "idx-financials"
    assert catalog.collections[0].sheet_names == ["Income Statement"]
    assert async_result == result
    store.list_data_scopes.assert_called_once_with()
    store.list_data_scopes_async.assert_awaited_once_with()


def test_data_scope_rejects_empty_database_catalog() -> None:
    store = MagicMock()
    store.list_data_scopes.return_value = []
    store.list_data_scopes_async = AsyncMock(return_value=[])
    with pytest.raises(ModuleExecutionError, match="data scope가 없습니다"):
        PgVectorDataScopeModule(store).run(PgVectorDataScopeInputDTO())
    with pytest.raises(ModuleExecutionError, match="data scope가 없습니다"):
        asyncio.run(PgVectorDataScopeModule(store).run_async(PgVectorDataScopeInputDTO()))
