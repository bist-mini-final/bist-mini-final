from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.providers.openai_responses import OpenAIResponseResult
from modules.common.base_module import ModuleExecutionError, QueryContextDTO
from modules.query.decomposer import SubqueriesDTO, SubqueryItem
from modules.query.llm_query_router import (
    LlmQueryRouterInputDTO,
    LlmQueryRouterModule,
    RetrievalPlanDTO,
)
from modules.storage.pgvector_data_scope import DataScopeCatalogDTO, DataScopeDTO


def _scope(index_id: str, company: str, sheet: str) -> DataScopeDTO:
    return DataScopeDTO(
        index_id=index_id,
        file_name=f"{company}.xlsx",
        workbook_hash=f"hash-{index_id}",
        company_name=company,
        sheet_names=[sheet],
        model="text-embedding-3-small",
        dimension=1536,
        document_count=100,
    )


def _input() -> LlmQueryRouterInputDTO:
    return LlmQueryRouterInputDTO(
        query_input=SubqueriesDTO(
            query_context=QueryContextDTO(
                question_id="q1",
                question_text="삼성전자 매출과 현대자동차 부채를 비교해줘",
            ),
            items=[
                SubqueryItem(company="삼성전자", sheet="손익계산서", row_header="매출"),
                SubqueryItem(company="현대자동차", sheet="재무상태표", row_header="부채"),
            ],
        ),
        scope_catalog=DataScopeCatalogDTO(
            collections=[
                _scope("idx-samsung", "삼성전자", "손익계산서"),
                _scope("idx-hyundai", "현대자동차", "재무상태표"),
            ]
        ),
    )


def test_router_maps_each_subquery_to_concrete_collection() -> None:
    client = MagicMock()
    client.create_response.return_value = OpenAIResponseResult(
        response_id="resp-router",
        content=(
            '{"routes":['
            '{"subquery_index":0,"index_ids":["idx-samsung"]},'
            '{"subquery_index":1,"index_ids":["idx-hyundai"]}'
            "]}"
        ),
        usage={"prompt_tokens": 60, "completion_tokens": 20, "total_tokens": 80},
        latency_seconds=0.2,
    )
    result = LlmQueryRouterModule(client).run(_input())
    plan = RetrievalPlanDTO.model_validate(result)

    assert plan.selected_index_ids == ["idx-samsung", "idx-hyundai"]
    assert plan.routes[0].subquery.company == "삼성전자"
    assert plan.routes[1].collections[0].index_id == "idx-hyundai"
    assert plan.metrics["kind"] == "llm_collection_router"

    client.create_response_async = AsyncMock(return_value=client.create_response.return_value)
    async_result = asyncio.run(LlmQueryRouterModule(client).run_async(_input()))
    assert RetrievalPlanDTO.model_validate(async_result).selected_index_ids == [
        "idx-samsung",
        "idx-hyundai",
    ]
    client.create_response_async.assert_awaited_once()


def test_router_rejects_collection_not_present_in_db_catalog() -> None:
    client = MagicMock()
    client.create_response.return_value = OpenAIResponseResult(
        response_id="resp-router-invalid",
        content=(
            '{"routes":['
            '{"subquery_index":0,"index_ids":["invented"]},'
            '{"subquery_index":1,"index_ids":["idx-hyundai"]}'
            "]}"
        ),
        usage={},
        latency_seconds=0,
    )
    with pytest.raises(ModuleExecutionError, match="catalog에 없는 collection"):
        LlmQueryRouterModule(client).run(_input())


def test_router_skips_provider_call_for_empty_subquery_set() -> None:
    client = MagicMock()
    input_data = _input()
    input_data.query_input.items = []
    result = LlmQueryRouterModule(client).run(input_data)

    assert result["routes"] == []
    client.create_response.assert_not_called()
