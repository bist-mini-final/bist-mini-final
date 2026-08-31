from __future__ import annotations

import pytest

from modules.common.base_module import DocumentContextDTO, QueryContextDTO
from modules.common.exceptions import ModuleExecutionError
from modules.retrieval.pgvector_retriever import (
    RankedSearchCandidateDTO,
    RankedSearchResultDTO,
)
from modules.retrieval.rrf_fusion import (
    RrfFusionConfigDTO,
    RrfFusionInputDTO,
    RrfFusionModule,
)


def test_rrf_fusion_successful_combination():
    module = RrfFusionModule()
    query_ctx = QueryContextDTO(question_id="q1", question_text="영업이익")
    doc_ctx = DocumentContextDTO(file_name="test.xlsx", workbook_hash="h1", index_id="idx_1")

    bm25_res = RankedSearchResultDTO(
        query_context=query_ctx,
        document_context=doc_ctx,
        items=[
            RankedSearchCandidateDTO(
                rank=1,
                index_id="idx_1",
                cell_id="c1",
                sheet_name="Income_Statement",
                cell_coord="B2",
                score=0.9,
                text="cell 1",
                matched_subquery="q",
            ),
            RankedSearchCandidateDTO(rank=2, index_id="idx_1", cell_id="c2", score=0.8, text="cell 2", matched_subquery="q"),
        ],
    )
    dense_res = RankedSearchResultDTO(
        query_context=query_ctx,
        document_context=doc_ctx,
        items=[
            RankedSearchCandidateDTO(
                rank=1,
                index_id="idx_1",
                cell_id="c1",
                sheet_name="Income_Statement",
                cell_coord="B2",
                score=0.95,
                text="cell 1",
                matched_subquery="q",
            ),
            RankedSearchCandidateDTO(rank=2, index_id="idx_1", cell_id="c3", score=0.7, text="cell 3", matched_subquery="q"),
        ],
    )

    result = module.execute(
        RrfFusionInputDTO(bm25_result=bm25_res, dense_result=dense_res),
        config=RrfFusionConfigDTO(rrf_k=60, top_k=10),
    )

    assert "items" in result
    assert len(result["items"]) == 3
    # c1 is ranked 1 in both, so it must be top
    assert result["items"][0]["cell_id"] == "c1"
    assert result["items"][0]["sheet_name"] == "Income_Statement"
    assert result["items"][0]["cell_coord"] == "B2"
    assert result["items"][0]["rank"] == 1


def test_rrf_fusion_keeps_same_coordinate_from_different_sheets():
    module = RrfFusionModule()
    query_ctx = QueryContextDTO(question_id="q1", question_text="compare")
    doc_ctx = DocumentContextDTO(file_name="test.xlsx", workbook_hash="h1", index_id="idx_1")
    dense_res = RankedSearchResultDTO(
        query_context=query_ctx,
        document_context=doc_ctx,
        items=[
            RankedSearchCandidateDTO(
                rank=1,
                index_id="idx_1",
                cell_id="B2",
                sheet_name="Income_Statement",
                cell_coord="B2",
                score=0.9,
                text="revenue",
                matched_subquery="q",
            ),
            RankedSearchCandidateDTO(
                rank=2,
                index_id="idx_1",
                cell_id="B2",
                sheet_name="Balance_Sheet",
                cell_coord="B2",
                score=0.8,
                text="assets",
                matched_subquery="q",
            ),
        ],
    )
    empty_bm25 = RankedSearchResultDTO(
        query_context=query_ctx,
        document_context=doc_ctx,
        items=[],
    )

    result = module.execute(
        RrfFusionInputDTO(bm25_result=empty_bm25, dense_result=dense_res),
        config=RrfFusionConfigDTO(rrf_k=60, top_k=10),
    )

    assert [(item["sheet_name"], item["cell_id"]) for item in result["items"]] == [
        ("Income_Statement", "B2"),
        ("Balance_Sheet", "B2"),
    ]


def test_rrf_rejects_cross_document_fusion():
    module = RrfFusionModule()
    query_ctx = QueryContextDTO(question_id="q1", question_text="영업이익")

    bm25_res = RankedSearchResultDTO(
        query_context=query_ctx,
        document_context=DocumentContextDTO(file_name="doc1.xlsx", workbook_hash="h1", index_id="idx_1"),
        items=[],
    )
    dense_res = RankedSearchResultDTO(
        query_context=query_ctx,
        document_context=DocumentContextDTO(file_name="doc2.xlsx", workbook_hash="h2", index_id="idx_2"),
        items=[],
    )

    with pytest.raises(ModuleExecutionError):
        module.execute(RrfFusionInputDTO(bm25_result=bm25_res, dense_result=dense_res))
