"""Unit and integration tests for Direct Cell Answer Refiner Module."""

import pytest
from backend.modules.answer_refiner import (
    AnswerRefinerModule,
    AnswerRefinerInputDTO,
    DirectCellDTO,
    _col_to_num,
    _num_to_col,
    _split_cell_coord,
)
from backend.modules.reader import AnswerDTO, ApiUsageDTO
from backend.modules.data_lineage import QueryContextDTO, DocumentContextDTO
from backend.llm.chat_completion import ChatCompletionResult


class FakeCellStore:
    def fetch_cells_by_metadata(self, cell_identifiers, workbook_hash=None, **_kwargs):
        assert workbook_hash == "6f4a07f1f3023def767a68ffb8531c7f3867f3f622555aeef2d84d7390c6cae4"
        return [
            {
                "cell_id": "IS Cell O17",
                "sheet_name": "IS",
                "cell_coord": "O17",
                "cell_value": "709",
                "row_header": ["Financial revenue"],
                "column_header": ["2024"],
                "source_text": "Financial revenue | 2024 | 709",
            }
        ]


class FakeCompletionClient:
    api_key = "test"

    def complete_with_metadata(self, model, messages, response_format=None):
        return ChatCompletionResult(
            content=(
                '{"refined_answer":"교정된 답변 [IS:O17]",'
                '"refinement_summary":"직접 셀을 확인했습니다."}'
            ),
            usage={
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "cached_tokens": 0,
                "reasoning_tokens": 0,
                "total_tokens": 15,
            },
            latency_seconds=0.01,
        )


def test_excel_coordinate_utilities():
    """Verify Excel column-to-number and spatial splitting utilities."""
    assert _col_to_num("A") == 1
    assert _col_to_num("O") == 15
    assert _col_to_num("P") == 16
    assert _col_to_num("Q") == 17
    assert _col_to_num("AA") == 27

    assert _num_to_col(1) == "A"
    assert _num_to_col(15) == "O"
    assert _num_to_col(16) == "P"
    assert _num_to_col(17) == "Q"

    assert _split_cell_coord("O50") == ("O", 50)
    assert _split_cell_coord("IS:P16") is None
    assert _split_cell_coord("Q16") == ("Q", 16)


def test_spatial_neighbor_expansion():
    """Verify that O50 expands to N50, P50, Q50, R50 for timeline continuity."""
    module = AnswerRefinerModule()
    neighbors = module._expand_spatial_neighbors("O50", radius=3)

    assert "O50" in neighbors
    assert "P50" in neighbors  # 2025
    assert "Q50" in neighbors  # 2025 LTM
    assert "R50" in neighbors  # 2026E
    assert "N50" in neighbors  # 2023


def test_candidate_cell_extraction_from_text():
    """Verify regex and named cell pattern extraction."""
    module = AnswerRefinerModule()
    question = "IBM의 2025년 환율 관련 손익과 현금 및 현금성자산 차이는 얼마야?"
    initial_answer = (
        "2024년 기준 환율 관련 손익은 20백만 달러입니다 [IS Cell O50]. "
        "현금 및 현금성자산은 13,947백만 달러입니다 [BS Cell O16]. "
        "2025년 환율 손익은 NA이므로 계산할 수 없습니다."
    )

    candidates = module._extract_candidate_cell_ids(
        question=question,
        initial_answer=initial_answer,
        spatial_radius=2,
    )

    # Base cells
    assert "O50" in candidates
    assert "O16" in candidates

    # Expanded 2025/LTM cells
    assert "P50" in candidates
    assert "Q50" in candidates
    assert "P16" in candidates
    assert "Q16" in candidates


def test_candidate_cell_extraction_ignores_year_and_quarter_tokens():
    module = AnswerRefinerModule()
    candidates = module._extract_candidate_cell_ids(
        question="FY2025 EPS2024와 Q3 실적을 비교해줘",
        initial_answer="근거는 [IS Cell O50]입니다.",
        spatial_radius=0,
    )

    assert candidates == ["O50"]


def test_answer_refiner_module_contract():
    """Verify module definition and schema compliance."""
    module = AnswerRefinerModule()
    contract = module.contract()

    assert contract["type"] == "answer_refiner"
    assert contract["category"] == "Output"
    assert "answer_json" in contract["inputs"]
    assert "refined_answer_json" in contract["outputs"]
    assert "spatial_column_radius" in contract["config_fields"]


def test_answer_refiner_execution_with_mock_data():
    """Verify end-to-end execution of AnswerRefinerModule."""
    module = AnswerRefinerModule(pgvector_store=FakeCellStore())

    mock_input = {
        "answer_json": {
            "query_context": {
                "question_id": "QUERY-TEST-1234",
                "question_text": "IBM의 2025년 금융부문 매출과 기타유동자산 차이는 얼마야?",
            },
            "document_context": {
                "file_name": "SPG_Company_KeyStats_v4.xlsm",
                "workbook_hash": "6f4a07f1f3023def767a68ffb8531c7f3867f3f622555aeef2d84d7390c6cae4",
            },
            "model": "gpt-5.6-luna",
            "answer": "2024년 금융부문 매출은 709백만 달러 [IS Cell O17], 기타유동자산은 1,562백만 달러 [BS Cell O33]입니다.",
            "api_usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
            },
            "latency_seconds": 1.2,
            "estimated_cost_usd": 0.0001,
        },
        "spatial_column_radius": 2,
        "max_direct_cells": 10,
    }

    result = module.execute(mock_input)

    assert "refined_answer_json" in result
    refined = result["refined_answer_json"]

    assert refined["query_context"]["question_id"] == "QUERY-TEST-1234"
    assert refined["initial_answer"].startswith("2024년")
    assert isinstance(refined["refined_answer"], str)
    assert len(refined["refined_answer"]) > 0
    assert isinstance(refined["refinement_summary"], str)
    assert isinstance(refined["direct_cells"], list)
    assert refined["latency_seconds"] >= 0.0


def test_answer_refiner_uses_chat_completion_metadata_contract():
    module = AnswerRefinerModule(
        pgvector_store=FakeCellStore(),
        completion_client=FakeCompletionClient(),
    )
    result = module.execute(
        {
            "answer_json": {
                "query_context": {
                    "question_id": "QUERY-TEST-1234",
                    "question_text": "IBM의 금융부문 매출은 얼마야?",
                },
                "document_context": {
                    "file_name": "SPG_Company_KeyStats_v4.xlsm",
                    "workbook_hash": "6f4a07f1f3023def767a68ffb8531c7f3867f3f622555aeef2d84d7390c6cae4",
                },
                "model": "gpt-5.6-luna",
                "answer": "709입니다 [IS Cell O17].",
                "api_usage": {},
                "latency_seconds": 0,
                "estimated_cost_usd": 0,
            },
            "enable_auto_cell_discovery": False,
        }
    )["refined_answer_json"]

    assert result["refined_answer"] == "교정된 답변 [IS:O17]"
    assert result["api_usage"]["total_tokens"] == 15
