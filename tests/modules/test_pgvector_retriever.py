from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from backend.domains.data_sources.infrastructure.pgvector import PgVectorStore
from modules.common.base_module import QueryContextDTO
from modules.embedding.query_embedder import EmbeddingsDTO, RoutedEmbeddingDTO
from modules.query.decomposer import SubqueryItem
from modules.retrieval.pgvector_retriever import (
    PgVectorRetrieverConfigDTO,
    PgVectorRetrieverInputDTO,
    PgVectorRetrieverModule,
)
from modules.storage.pgvector_data_scope import DataScopeDTO


def test_dense_retrieval_searches_only_the_routed_collection() -> None:
    store = MagicMock()
    document = MagicMock()
    document.page_content = "Cell 1 content"
    document.metadata = {"cell_id": "cell_1"}
    store.similarity_search_by_vector_with_score.return_value = [(document, 0.15)]
    scope = DataScopeDTO(
        index_id="idx-routed",
        file_name="sample.xlsx",
        workbook_hash="hash-1",
        company_name="Example Corp",
        sheet_names=["Financials"],
        model="text-embedding-3-small",
        dimension=1536,
        document_count=100,
    )
    subquery = SubqueryItem(
        company="Example Corp",
        sheet="Financials",
        row_header="Revenue",
        text="Revenue",
    )
    embeddings = EmbeddingsDTO(
        query_context=QueryContextDTO(question_id="q1", question_text="Revenue"),
        items=[
            RoutedEmbeddingDTO(
                subquery_index=0,
                subquery=subquery,
                collection=scope,
                vector=[0.1] * 1536,
            )
        ],
    )
    module = PgVectorRetrieverModule(store)
    input_data = PgVectorRetrieverInputDTO(query_input=embeddings)
    config = PgVectorRetrieverConfigDTO(top_k=5)
    result = module.run(
        input_data,
        config,
    )

    assert result["items"][0]["index_id"] == "idx-routed"
    assert result["items"][0]["cell_id"] == "cell_1"
    store.similarity_search_by_vector_with_score.assert_called_once_with(
        collection_name="idx-routed",
        embedding=[0.1] * 1536,
        k=5,
        sheet_names=["Financials"],
        company_name="Example Corp",
    )

    store.similarity_search_by_vector_with_score_async = AsyncMock(return_value=[(document, 0.15)])
    async_result = asyncio.run(module.run_async(input_data, config))
    assert async_result["items"] == result["items"]
    store.similarity_search_by_vector_with_score_async.assert_awaited_once()


def test_direct_dense_sql_uses_single_character_like_escape() -> None:
    class Cursor:
        def __init__(self) -> None:
            self.sql = ""
            self.params = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql, params):
            self.sql = sql
            self.params = list(params)

        def fetchall(self):
            return []

    class Connection:
        def __init__(self, cursor: Cursor) -> None:
            self._cursor = cursor

        def cursor(self):
            return self._cursor

        def close(self):
            return None

    cursor = Cursor()
    store = PgVectorStore()
    store._collection_uuid_cache["idx-test"] = "00000000-0000-0000-0000-000000000001"
    store._read_connection = lambda: Connection(cursor)  # type: ignore[method-assign]

    result = store.similarity_search_by_vector_with_score(
        "idx-test",
        [0.1, 0.2],
        company_name="A!B%_Corp",
    )

    assert result == []
    assert "ESCAPE '!'" in cursor.sql
    assert "%A!!B!%!_Corp%" in cursor.params
