from __future__ import annotations

from unittest.mock import MagicMock

from modules.common.base_module import QueryContextDTO
from modules.query.decomposer import SubqueryItem
from modules.query.llm_query_router import RetrievalPlanDTO, RoutedSubqueryDTO
from modules.retrieval.postgres_native_keyword_retriever import (
    PostgresNativeKeywordRetrieverInputDTO,
    PostgresNativeKeywordRetrieverModule,
    _clean_tsquery_term,
    _escape_like_term,
)
from modules.storage.pgvector_data_scope import DataScopeDTO


def test_keyword_retriever_uses_only_router_selected_collection() -> None:
    store = MagicMock()
    connection = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        (
            "2023 Revenue 120",
            {
                "cell_id": "c1",
                "company_name": "Example Corp",
                "sheet_name": "Financials",
            },
            0.85,
            "idx-routed",
        )
    ]
    connection.cursor.return_value.__enter__.return_value = cursor
    store._read_connection.return_value = connection
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
    plan = RetrievalPlanDTO(
        query_context=QueryContextDTO(question_id="q1", question_text="Revenue"),
        routes=[
            RoutedSubqueryDTO(
                subquery_index=0,
                subquery=SubqueryItem(
                    company="Example Corp",
                    sheet="Financials",
                    row_header="Revenue",
                    column_header="2023",
                ),
                collections=[scope],
            )
        ],
    )
    result = PostgresNativeKeywordRetrieverModule(store).run(
        PostgresNativeKeywordRetrieverInputDTO(retrieval_plan=plan)
    )

    assert result["items"][0]["index_id"] == "idx-routed"
    assert result["items"][0]["cell_id"] == "Example Corp:c1"
    sql, params = cursor.execute.call_args_list[0].args
    assert "collection.name = ANY(%s)" in sql
    assert "ESCAPE '!'" in sql
    assert params[1] == ["idx-routed"]


def test_like_scope_escaping_uses_one_character_escape() -> None:
    assert _escape_like_term("A!B%_Corp") == "A!!B!%!_Corp"


def test_structured_keyword_query_uses_metric_and_period_only() -> None:
    assert _clean_tsquery_term(
        "Company: Codex Low Cost Test Corp | Sheet: Financials | "
        "Row Header: Revenue | Column Header: FY2025 | Cell Value: ?"
    ) == "Revenue FY2025"
