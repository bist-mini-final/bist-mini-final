from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock

from backend.domains.data_sources.infrastructure.pgvector import (
    VECTOR_INDEX_STRATEGY,
    VECTOR_PARTITION_STRATEGY,
    PgVectorStore,
)


class _Cursor:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, statement: str) -> None:
        self.statements.append(statement)


class _Connection:
    def __init__(self) -> None:
        self.cursor_instance = _Cursor()
        self.closed = False

    def cursor(self) -> _Cursor:
        return self.cursor_instance

    def close(self) -> None:
        self.closed = True


def test_collection_index_uses_binary_quantization_and_exact_vector_is_retained() -> None:
    collection_uuid = "a7e494ec-7828-4671-908f-0a222fd90d90"
    connection = _Connection()
    store = PgVectorStore("postgresql://unused")
    cast(Any, store)._collection_uuid = lambda _name: collection_uuid
    cast(Any, store)._read_connection = lambda: connection

    index_name = store.ensure_collection_vector_index("idx-test", 3072)

    statement = connection.cursor_instance.statements[0]
    assert index_name == f"idx_lc_hnsw_bq_c_{collection_uuid.replace('-', '')}_3072"
    assert "binary_quantize(embedding)::bit(3072)" in statement
    assert "bit_hamming_ops" in statement
    assert "embedding::halfvec" not in statement
    assert "WHERE collection_id" in statement
    assert connection.closed is True
    assert VECTOR_INDEX_STRATEGY == "binary_quantized_hnsw_exact_rerank"
    assert VECTOR_PARTITION_STRATEGY == "collection_local_partial_indexes"


def test_search_encodes_query_with_the_collection_model() -> None:
    store = PgVectorStore("postgresql://unused")
    encoder = MagicMock()
    encoder.encode_for_model.return_value = [[0.1, 0.2, 0.3]]
    cast(Any, store).similarity_search_by_vector_with_score = MagicMock(return_value=[])

    result = store.search(
        "idx-test",
        query_text="Total Revenue 2024",
        model_name="text-embedding-3-large",
        embedding_encoder=encoder,
        limit=5,
    )

    assert result == []
    encoder.encode_for_model.assert_called_once_with(
        ["Total Revenue 2024"],
        "text-embedding-3-large",
    )
    encoder.encode.assert_not_called()
