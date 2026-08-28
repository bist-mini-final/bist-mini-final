from __future__ import annotations

import asyncio

from modules.common.base_module import QueryContextDTO
from modules.embedding.query_embedder import EmbedderInputDTO, EmbedderModule
from modules.query.decomposer import SubqueryItem
from modules.query.llm_query_router import RetrievalPlanDTO, RoutedSubqueryDTO
from modules.storage.pgvector_data_scope import DataScopeDTO


def _scope(index_id: str, model: str, dimension: int) -> DataScopeDTO:
    return DataScopeDTO(
        index_id=index_id,
        file_name=f"{index_id}.xlsx",
        workbook_hash=f"hash-{index_id}",
        company_name="Example Corp",
        sheet_names=["Financials"],
        model=model,
        dimension=dimension,
        document_count=10,
    )


def test_query_embedder_batches_by_collection_model_contract() -> None:
    class Encoder:
        def __init__(self) -> None:
            self.calls: list[tuple[list[str], str]] = []
            self.async_calls: list[tuple[list[str], str]] = []
            self.last_usage = {"total_tokens": 1}

        def encode_for_model(
            self,
            queries: list[str],
            model_name: str,
        ) -> list[list[float]]:
            self.calls.append((queries, model_name))
            dimension = 1536 if model_name.endswith("small") else 3072
            return [[0.1] * dimension for _ in queries]

        async def encode_for_model_async(
            self,
            queries: list[str],
            model_name: str,
            _batch_size: int,
        ) -> list[list[float]]:
            self.async_calls.append((queries, model_name))
            dimension = 1536 if model_name.endswith("small") else 3072
            return [[0.1] * dimension for _ in queries]

    encoder = Encoder()
    plan = RetrievalPlanDTO(
        query_context=QueryContextDTO(question_id="q1", question_text="Revenue"),
        routes=[
            RoutedSubqueryDTO(
                subquery_index=0,
                subquery=SubqueryItem(row_header="Revenue", text="Revenue"),
                collections=[
                    _scope("idx-small", "text-embedding-3-small", 1536),
                    _scope("idx-large", "text-embedding-3-large", 3072),
                ],
            )
        ],
    )
    result = EmbedderModule(encoder).run(EmbedderInputDTO(retrieval_plan=plan))

    assert len(result["items"]) == 2
    assert [item["collection"]["index_id"] for item in result["items"]] == [
        "idx-large",
        "idx-small",
    ]
    assert len(result["items"][0]["vector"]) == 3072
    assert len(result["items"][1]["vector"]) == 1536
    assert encoder.calls == [
        (["Revenue"], "text-embedding-3-small"),
        (["Revenue"], "text-embedding-3-large"),
    ]

    async_result = asyncio.run(
        EmbedderModule(encoder).run_async(EmbedderInputDTO(retrieval_plan=plan))
    )
    assert async_result["items"] == result["items"]
    assert encoder.async_calls == encoder.calls
