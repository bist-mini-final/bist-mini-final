from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.platform.openai.responses import OpenAIResponseResult
from modules.common.base_module import ModuleExecutionError, QueryContextDTO
from modules.query.contracts import RetrievalPlanDTO, SubqueryItem
from modules.query.decomposer import DecomposerConfigDTO, DecomposerInputDTO, DecomposerModule
from modules.storage.pgvector_data_scope import DataScopeCatalogDTO, DataScopeDTO


def _scope(index_id: str, company: str, ticker: str, sheet: str) -> DataScopeDTO:
    return DataScopeDTO(
        index_id=index_id,
        file_name=f"{company}.xlsx",
        workbook_hash=f"hash-{index_id}",
        company_name=company,
        ticker=ticker,
        sheet_names=[sheet],
        model="text-embedding-3-small",
        dimension=1536,
        document_count=100,
    )


def _input() -> DecomposerInputDTO:
    return DecomposerInputDTO(
        query_context=QueryContextDTO(
            question_id="q1",
            question_text="ame soft 2024 total revenue와 현대차 2023 총부채를 알려줘",
        ),
        scope_catalog=DataScopeCatalogDTO(
            collections=[
                _scope("idx-amesoft", "AmeSoft", "AME", "Income_Statement"),
                _scope("idx-hyundai", "현대자동차", "005380", "Balance_Sheet"),
            ]
        ),
    )


def test_subquery_item_serialization() -> None:
    item = SubqueryItem(
        company="삼성전자",
        sheet="손익계산서",
        row_header="영업이익",
        column_header="2023",
        cell_value="?",
    )

    serialized = item.to_serialized_query()

    assert "Company: 삼성전자" in serialized
    assert "Sheet: 손익계산서" in serialized
    assert "Row Header: 영업이익" in serialized
    assert "Column Header: 2023" in serialized
    assert "Cell Value: ?" in serialized


def test_decomposer_builds_catalog_scoped_plan_and_canonicalizes_aliases() -> None:
    client = MagicMock()
    client.create_response.return_value = OpenAIResponseResult(
        response_id="resp-decomposer",
        content=(
            '{"items":['
            '{"company":"ame soft","sheet":"Income Statement",'
            '"row_header":"Total Revenue","column_header":"FY2024",'
            '"cell_value":"?","index_ids":["idx-amesoft"]},'
            '{"company":"현대자동차","sheet":"Balance Sheet",'
            '"row_header":"Total Liabilities","column_header":"FY2023",'
            '"cell_value":"?","index_ids":["idx-hyundai"]}'
            '],"unresolved_companies":[]}'
        ),
        usage={"prompt_tokens": 50, "completion_tokens": 30, "total_tokens": 80},
        latency_seconds=0.2,
    )
    module = DecomposerModule(client)

    result = module.run(_input(), DecomposerConfigDTO())
    plan = RetrievalPlanDTO.model_validate(result)

    assert plan.selected_index_ids == ["idx-amesoft", "idx-hyundai"]
    assert plan.routes[0].subquery.company == "AmeSoft"
    assert plan.routes[0].subquery.sheet == "Income_Statement"
    assert plan.routes[1].subquery.company == "현대자동차"
    assert plan.routes[1].subquery.sheet == "Balance_Sheet"
    assert plan.metrics["kind"] == "scope_aware_decomposer"
    prompt = client.create_response.call_args.kwargs["input_items"]
    assert "idx-amesoft" in str(prompt)
    assert "AmeSoft" in str(prompt)

    client.create_response_async = AsyncMock(return_value=client.create_response.return_value)
    async_result = asyncio.run(module.run_async(_input(), DecomposerConfigDTO()))
    assert RetrievalPlanDTO.model_validate(async_result).model_dump(mode="json") == result
    client.create_response_async.assert_awaited_once()


def test_decomposer_preserves_total_revenue_meaning_for_explicit_korean_query() -> None:
    client = MagicMock()
    client.create_response.return_value = OpenAIResponseResult(
        response_id="resp-revenue-alias",
        content=(
            '{"items":[{"company":"AmeSoft","sheet":"Income Statement",'
            '"row_header":"Revenue","column_header":"FY2024","cell_value":"?",'
            '"index_ids":["idx-amesoft"]}],"unresolved_companies":[]}'
        ),
        usage={},
        latency_seconds=0,
    )
    input_data = DecomposerInputDTO(
        query_context=QueryContextDTO(
            question_id="q-total-revenue",
            question_text="AmeSoft의 2024년 총매출액을 알려줘",
        ),
        scope_catalog=DataScopeCatalogDTO(
            collections=[
                _scope("idx-amesoft", "AmeSoft", "AME", "Income_Statement"),
            ]
        ),
    )

    plan = RetrievalPlanDTO.model_validate(DecomposerModule(client).run(input_data))

    assert plan.routes[0].subquery.row_header == "Total Revenue"


def test_decomposer_keeps_bare_korean_revenue_narrow() -> None:
    assert (
        DecomposerModule._canonical_row_header(
            "AmeSoft의 2024년 매출액을 알려줘",
            "Revenue",
        )
        == "Revenue"
    )


def test_decomposer_keeps_qualified_revenue_metric() -> None:
    assert (
        DecomposerModule._canonical_row_header(
            "AmeSoft의 서비스 부문 매출을 알려줘",
            "Revenue",
        )
        == "Revenue"
    )


@pytest.mark.parametrize(
    ("question", "model_row_header", "expected"),
    [
        (
            "AmeSoft의 2024년 총부채(Total Liabilities)를 알려줘",
            "Total Debt",
            "Total Liabilities",
        ),
        (
            "AmeSoft의 2024년 총차입금(Total Debt)을 알려줘",
            "Total Liabilities",
            "Total Debt",
        ),
    ],
)
def test_decomposer_preserves_explicit_liability_and_debt_distinction(
    question: str,
    model_row_header: str,
    expected: str,
) -> None:
    assert DecomposerModule._canonical_row_header(question, model_row_header) == expected


def test_decomposer_uses_explicit_sheet_as_single_route_hard_constraint() -> None:
    client = MagicMock()
    client.create_response.return_value = OpenAIResponseResult(
        response_id="resp-explicit-cash-flow",
        content=(
            '{"items":[{"company":"AmeSoft","sheet":"Balance Sheet",'
            '"row_header":"Capital Expenditures","column_header":"FY2024",'
            '"cell_value":"?","index_ids":["idx-amesoft"]}],'
            '"unresolved_companies":[]}'
        ),
        usage={},
        latency_seconds=0,
    )
    input_data = DecomposerInputDTO(
        query_context=QueryContextDTO(
            question_id="q-explicit-cash-flow",
            question_text="AmeSoft의 현금흐름표상 2024년 자본지출을 알려줘",
        ),
        scope_catalog=DataScopeCatalogDTO(
            collections=[
                _scope("idx-amesoft", "AmeSoft", "AME", "Cash_Flow"),
            ]
        ),
    )

    plan = RetrievalPlanDTO.model_validate(DecomposerModule(client).run(input_data))

    assert plan.routes[0].subquery.sheet == "Cash_Flow"


def test_decomposer_does_not_apply_one_sheet_phrase_to_every_multi_route_item() -> None:
    client = MagicMock()
    client.create_response.return_value = OpenAIResponseResult(
        response_id="resp-mixed-sheet-operands",
        content=(
            '{"items":['
            '{"company":"AmeSoft","sheet":"Cash Flow",'
            '"row_header":"Change in Accounts Receivable",'
            '"column_header":"FY2024","cell_value":"?",'
            '"index_ids":["idx-amesoft-cf"]},'
            '{"company":"AmeSoft","sheet":"Balance Sheet",'
            '"row_header":"Total Liabilities","column_header":"FY2025",'
            '"cell_value":"?","index_ids":["idx-amesoft-bs"]}'
            '],"unresolved_companies":[]}'
        ),
        usage={},
        latency_seconds=0,
    )
    input_data = DecomposerInputDTO(
        query_context=QueryContextDTO(
            question_id="q-mixed-sheet-operands",
            question_text=(
                "AmeSoft의 2024년 현금흐름표상 매출채권 변동과 "
                "2025년 총부채를 알려줘"
            ),
        ),
        scope_catalog=DataScopeCatalogDTO(
            collections=[
                _scope("idx-amesoft-cf", "AmeSoft", "AME", "Cash_Flow"),
                _scope("idx-amesoft-bs", "AmeSoft", "AME", "Balance_Sheet"),
            ]
        ),
    )

    plan = RetrievalPlanDTO.model_validate(DecomposerModule(client).run(input_data))

    assert [route.subquery.sheet for route in plan.routes] == [
        "Cash_Flow",
        "Balance_Sheet",
    ]


def test_decomposer_rejects_collection_not_present_in_catalog() -> None:
    client = MagicMock()
    client.create_response.return_value = OpenAIResponseResult(
        response_id="resp-invalid",
        content=(
            '{"items":[{"company":"AMETEK","sheet":"Income Statement",'
            '"row_header":"Revenue","column_header":"2024","cell_value":"?",'
            '"index_ids":["invented"]}],"unresolved_companies":[]}'
        ),
        usage={},
        latency_seconds=0,
    )

    with pytest.raises(ModuleExecutionError, match="catalog에 없는 collection"):
        DecomposerModule(client).run(_input())


def test_decomposer_repairs_unknown_id_when_server_fixed_one_scope() -> None:
    client = MagicMock()
    client.create_response.return_value = OpenAIResponseResult(
        response_id="resp-single-scope-typo",
        content=(
            '{"items":[{"company":"AmeSoft","sheet":"Income Statement",'
            '"row_header":"Short-Term Debt","column_header":"FY2021","cell_value":"?",'
            '"index_ids":["idx-ames0ft"]}],"unresolved_companies":[]}'
        ),
        usage={},
        latency_seconds=0,
    )
    single_scope = DecomposerInputDTO(
        query_context=QueryContextDTO(
            question_id="q-single",
            question_text="AmeSoft FY2021 short-term debt",
        ),
        scope_catalog=DataScopeCatalogDTO(
            collections=[
                _scope("idx-amesoft", "AmeSoft", "AME", "Balance_Sheet"),
            ]
        ),
    )

    plan = RetrievalPlanDTO.model_validate(DecomposerModule(client).run(single_scope))

    assert plan.selected_index_ids == ["idx-amesoft"]
    assert plan.metrics["repaired_scope_count"] == 1


def test_decomposer_repairs_all_unknown_ids_to_exact_company_in_multi_catalog() -> None:
    client = MagicMock()
    client.create_response.return_value = OpenAIResponseResult(
        response_id="resp-company-scoped-repair",
        content=(
            '{"items":[{"company":"AmeSoft","sheet":"Income Statement",'
            '"row_header":"Total Revenue","column_header":"FY2024","cell_value":"?",'
            '"index_ids":["idx-amesoftidx-hyundai"]}],"unresolved_companies":[]}'
        ),
        usage={},
        latency_seconds=0,
    )

    plan = RetrievalPlanDTO.model_validate(DecomposerModule(client).run(_input()))

    assert plan.selected_index_ids == ["idx-amesoft"]
    assert plan.metrics["repaired_scope_count"] == 1


def test_decomposer_ignores_false_unresolved_company_present_in_catalog() -> None:
    client = MagicMock()
    client.create_response.return_value = OpenAIResponseResult(
        response_id="resp-false-unresolved",
        content=(
            '{"items":[{"company":"AmeSoft","sheet":"Income Statement",'
            '"row_header":"Total Revenue","column_header":"FY2024","cell_value":"?",'
            '"index_ids":["idx-amesoft"]}],"unresolved_companies":["AmeSoft"]}'
        ),
        usage={},
        latency_seconds=0,
    )

    plan = RetrievalPlanDTO.model_validate(DecomposerModule(client).run(_input()))

    assert plan.selected_index_ids == ["idx-amesoft"]
    assert plan.metrics["decomposition_attempts"] == 1


def test_decomposer_retries_empty_plan_once_and_aggregates_metrics() -> None:
    client = MagicMock()
    client.create_response.side_effect = [
        OpenAIResponseResult(
            response_id="resp-empty",
            content='{"items":[],"unresolved_companies":[]}',
            usage={"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
            latency_seconds=0.1,
        ),
        OpenAIResponseResult(
            response_id="resp-retry",
            content=(
                '{"items":[{"company":"AmeSoft","sheet":"Income Statement",'
                '"row_header":"Total Revenue","column_header":"FY2024",'
                '"cell_value":"?","index_ids":["idx-amesoft"]}],'
                '"unresolved_companies":[]}'
            ),
            usage={"prompt_tokens": 20, "completion_tokens": 5, "total_tokens": 25},
            latency_seconds=0.2,
        ),
    ]

    plan = RetrievalPlanDTO.model_validate(DecomposerModule(client).run(_input()))

    assert plan.selected_index_ids == ["idx-amesoft"]
    assert plan.metrics["decomposition_attempts"] == 2
    assert plan.metrics["api_usage"]["prompt_tokens"] == 30
    assert plan.metrics["api_usage"]["completion_tokens"] == 7
    assert plan.metrics["latency_seconds"] == 0.3
    assert client.create_response.call_count == 2


def test_decomposer_reports_unresolved_company_without_substitution() -> None:
    client = MagicMock()
    client.create_response.return_value = OpenAIResponseResult(
        response_id="resp-unresolved",
        content='{"items":[],"unresolved_companies":["AMETEK"]}',
        usage={},
        latency_seconds=0,
    )

    with pytest.raises(ModuleExecutionError, match="AMETEK"):
        DecomposerModule(client).run(_input())


def test_decomposer_keeps_catalog_routes_when_attachment_owns_unmatched_company() -> None:
    client = MagicMock()
    client.create_response.return_value = OpenAIResponseResult(
        response_id="resp-external-company",
        content=(
            '{"items":[{"company":"AmeSoft","sheet":"Income Statement",'
            '"row_header":"Total Revenue","column_header":"FY2024",'
            '"cell_value":"?","index_ids":["idx-amesoft"]}],'
            '"unresolved_companies":["Orbixa"],"external_context_companies":[]}'
        ),
        usage={},
        latency_seconds=0,
    )
    input_data = _input().model_copy(deep=True)
    input_data.query_context.question_text = (
        "AmeSoft와 Orbixa의 2024년 매출을 비교해줘"
    )
    input_data.query_context.external_context_sources = ["orbixa.xlsx"]

    plan = RetrievalPlanDTO.model_validate(DecomposerModule(client).run(input_data))

    assert plan.selected_index_ids == ["idx-amesoft"]
    assert plan.metrics["external_context_sources"] == ["orbixa.xlsx"]
    assert plan.metrics["external_context_companies"] == ["Orbixa"]
    prompt = client.create_response.call_args.kwargs["input_items"]
    assert "orbixa.xlsx" in str(prompt)


def test_decomposer_repairs_blank_catalog_id_and_skips_attachment_route() -> None:
    client = MagicMock()
    client.create_response.return_value = OpenAIResponseResult(
        response_id="resp-mixed-blank-index",
        content=(
            '{"items":['
            '{"company":"Nexora Labs","sheet":"Income Statement",'
            '"row_header":"Total Revenue","column_header":"Latest",'
            '"cell_value":"?","index_ids":[""]},'
            '{"company":"Meridian Logic","sheet":"Income Statement",'
            '"row_header":"Total Revenue","column_header":"Latest",'
            '"cell_value":"?","index_ids":[""]}'
            '],"unresolved_companies":[],"external_context_companies":[]}'
        ),
        usage={},
        latency_seconds=0,
    )
    input_data = DecomposerInputDTO(
        query_context=QueryContextDTO(
            question_id="q-mixed",
            question_text="Nexora와 Meridian의 최근 매출을 비교해줘",
            external_context_sources=["SPG_Company_KeyStats_09_meridian_logic.xlsm"],
        ),
        scope_catalog=DataScopeCatalogDTO(
            collections=[
                _scope("idx-nexora", "Nexora Labs", "NXR", "Income Statement"),
                _scope("idx-amesoft", "AmeSoft", "AME", "Income Statement"),
            ]
        ),
    )

    plan = RetrievalPlanDTO.model_validate(DecomposerModule(client).run(input_data))

    assert plan.selected_index_ids == ["idx-nexora"]
    assert plan.routes[0].subquery.company == "Nexora Labs"
    assert plan.metrics["repaired_scope_count"] == 1
    assert plan.metrics["external_context_companies"] == ["Meridian Logic"]


def test_decomposer_rejects_hallucinated_company_bound_to_valid_scope() -> None:
    client = MagicMock()
    client.create_response.return_value = OpenAIResponseResult(
        response_id="resp-company-mismatch",
        content=(
            '{"items":[{"company":"AMETEK","sheet":"Income Statement",'
            '"row_header":"Revenue","column_header":"2024","cell_value":"?",'
            '"index_ids":["idx-amesoft"]}],"unresolved_companies":[]}'
        ),
        usage={},
        latency_seconds=0,
    )

    with pytest.raises(ModuleExecutionError, match="기업명과 선택 collection"):
        DecomposerModule(client).run(_input())
