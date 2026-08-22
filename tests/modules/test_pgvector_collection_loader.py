from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from modules.common.exceptions import ModuleExecutionError
from modules.storage.pgvector_collection_loader import (
    PgVectorCollectionLoaderInputDTO,
    PgVectorCollectionLoaderModule,
)


def test_collection_loader_flattens_metadata():
    mock_store = MagicMock()
    mock_db = MagicMock()

    mock_store.list_indexes.return_value = [
        {
            "index_id": "idx_samsung",
            "file_name": "samsung.xlsx",
            "workbook_hash": "hash_123",
            "model": "text-embedding-3-large",
            "dimension": 3072,
            "document_count": 100,
        }
    ]
    mock_db.fetch_collection_metadata.return_value = {
        "file_name": "samsung.xlsx",
        "workbook_hash": "hash_123",
        "model": "text-embedding-3-large",
        "dimension": 3072,
        "document_count": 100,
    }

    module = PgVectorCollectionLoaderModule(pgvector_store=mock_store, db_manager=mock_db)
    input_dto = PgVectorCollectionLoaderInputDTO(collection_names=["samsung.xlsx"])
    result = module.execute(input_dto)

    assert "document_output" in result
    assert "index_output" in result
    assert result["index_output"]["dimension"] == 3072
    assert result["index_output"]["document_count"] == 100
    assert result["index_output"]["index_id"] == "idx_samsung"


def test_collection_loader_rejects_empty_collections():
    mock_store = MagicMock()
    mock_db = MagicMock()
    module = PgVectorCollectionLoaderModule(pgvector_store=mock_store, db_manager=mock_db)

    input_dto = PgVectorCollectionLoaderInputDTO(collection_names=[])
    with pytest.raises(ModuleExecutionError):
        module.execute(input_dto)
