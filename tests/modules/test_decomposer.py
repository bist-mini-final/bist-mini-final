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
