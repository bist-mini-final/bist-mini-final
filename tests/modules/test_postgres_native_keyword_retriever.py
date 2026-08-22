from __future__ import annotations

from unittest.mock import MagicMock

from modules.common.base_module import QueryContextDTO
from modules.query.decomposer import SubqueriesDTO, SubqueryItem
from modules.retrieval.postgres_native_keyword_retriever import (
    PostgresNativeKeywordRetrieverConfigDTO,
    PostgresNativeKeywordRetrieverInputDTO,
    PostgresNativeKeywordRetrieverModule,
)
from modules.storage.pgvector_collection_loader import IndexOutputDTO


def test_postgres_native_keyword_retriever_execution():
    mock_store = MagicMock()
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [
        ("id-1", "2023 영업이익 65670억", {"cell_id": "c1", "company": "삼성전자"}, 0.85, "uuid-1")
    ]
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_store._read_connection.return_value = mock_conn

    retriever = PostgresNativeKeywordRetrieverModule(pgvector_store=mock_store)

    input_dto = PostgresNativeKeywordRetrieverInputDTO(
        query_input=SubqueriesDTO(
            query_context=QueryContextDTO(question_id="1", question_text="영업이익"),
            items=[
                SubqueryItem(
                    company="삼성전자",
                    sheet="손익계산서",
                    row_header="영업이익",
                    column_header="2023",
                    text="Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: ?",
                )
            ],
        ),
        index_input=IndexOutputDTO(
            index_id="idx_1",
            file_name="samsung.xlsx",
            workbook_hash="hash1",
            model="text-embedding-3-large",
            dimension=3072,
            document_count=100,
        ),
    )
    res = retriever.execute(input_dto, config=PostgresNativeKeywordRetrieverConfigDTO())

    assert "items" in res
    assert len(res["items"]) == 1
    assert res["items"][0]["cell_id"] == "c1"
    assert res["items"][0]["rank"] == 1
