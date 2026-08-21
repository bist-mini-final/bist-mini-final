"""Unit and integration tests for Direct Cell Answer Refiner Module (Pure LLM Spatial Reasoning)."""

import pytest
from backend.modules.answer_refiner import (
    AnswerRefinerModule,
    AnswerRefinerInputDTO,
    DirectCellDTO,
    CellCandidateDTO,
)
from backend.modules.reader import AnswerDTO, ApiUsageDTO
from backend.modules.data_lineage import QueryContextDTO, DocumentContextDTO
from backend.llm.chat_completion import ChatCompletionResult


class FakeCellStore:
    def __init__(self):
        self.cell_references = []

    def fetch_cells_by_metadata(
        self,
        cell_identifiers,
        workbook_hash=None,
        cell_references=None,
        **_kwargs,
    ):
        assert workbook_hash == "6f4a07f1f3023def767a68ffb8531c7f3867f3f622555aeef2d84d7390c6cae4"
        self.cell_references = cell_references or []
        return [
            {
                "cell_id": "IS Cell P17",
                "sheet_name": "Income_Statement",
                "cell_coord": "P17",
                "cell_value": "750",
                "row_header": ["Financial revenue"],
                "column_header": ["2025"],
                "source_text": "Financial revenue | 2025 | 750",
            },
            {
                "cell_id": "BS Cell P33",
                "sheet_name": "Balance_Sheet",
                "cell_coord": "P33",
                "cell_value": "1,600",
                "row_header": ["Other current assets"],
                "column_header": ["2025"],
                "source_text": "Other current assets | 2025 | 1600",
            },
        ]


class FakeReasoningCompletionClient:
    api_key = "test"

    def complete_with_metadata(self, model, messages, response_format=None):
        # If extractor system prompt is called
        system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
        if "spatial reasoning" in system_msg.lower() or "topology" in system_msg.lower():
            # Returns inferred candidate cell coordinates based on 2D layout reasoning
            return ChatCompletionResult(
                content='["IS:P17", "BS:P33"]',
                usage={
                    "prompt_tokens": 50,
                    "completion_tokens": 10,
                    "cached_tokens": 0,
                    "reasoning_tokens": 0,
                    "total_tokens": 60,
                },
                latency_seconds=0.01,
            )

        # Refiner completion prompt
        return ChatCompletionResult(
            content=(
                '{"refined_answer":"2025년 금융부문 매출은 750백만 달러 [Income_Statement:P17], '
                '기타유동자산은 1,600백만 달러 [Balance_Sheet:P33]이며 차이는 850백만 달러입니다.",'
                '"refinement_summary":"2025년 실적 셀(P17, P33)을 직접 조회하여 답변을 완성했습니다."}'
            ),
            usage={
                "prompt_tokens": 100,
                "completion_tokens": 40,
                "cached_tokens": 0,
                "reasoning_tokens": 0,
                "total_tokens": 140,
            },
            latency_seconds=0.02,
        )


def test_candidate_token_parsing():
    """Verify parsing and normalization of candidate cell representations."""
    sheet_codes = {"IS": "Income_Statement", "BS": "Balance_Sheet", "CF": "Cash_Flow"}

    # Dict candidate
    cand1 = AnswerRefinerModule._parse_candidate_token(
        {"cell_coord": "P50", "sheet_name": "IS"}, sheet_codes
    )
    assert cand1 is not None
    assert cand1.cell_coord == "P50"
    assert cand1.sheet_name == "Income_Statement"

    # Qualified string candidates
    cand2 = AnswerRefinerModule._parse_candidate_token("IS:O17", sheet_codes)
    assert cand2 is not None
    assert cand2.cell_coord == "O17"
    assert cand2.sheet_name == "Income_Statement"

    cand3 = AnswerRefinerModule._parse_candidate_token("Balance_Sheet!Q16", sheet_codes)
    assert cand3 is not None
    assert cand3.cell_coord == "Q16"
    assert cand3.sheet_name == "Balance_Sheet"

    # Standalone string candidate
    cand4 = AnswerRefinerModule._parse_candidate_token("P50", sheet_codes)
    assert cand4 is not None
    assert cand4.cell_coord == "P50"
    assert cand4.sheet_name is None

    # Invalid token
    assert AnswerRefinerModule._parse_candidate_token("", sheet_codes) is None
    assert AnswerRefinerModule._parse_candidate_token(12345, sheet_codes) is None


def test_llm_spatial_reasoning_candidate_inference():
    """Verify that candidate cells are inferred via LLM spatial reasoning."""
    module = AnswerRefinerModule(completion_client=FakeReasoningCompletionClient())
    candidates, usage, cost = module._infer_candidate_cells(
        question="2025년 금융부문 매출과 기타유동자산 실적을 알려줘",
        initial_answer="2024년 금융부문 매출은 709 [IS Cell O17]이고 2025년 데이터는 누락되었습니다.",
        explicit_cell_ids=["CF:O19"],
    )

    coords = [c.cell_coord for c in candidates]
    sheets = [c.sheet_name for c in candidates]

    # Explicit cell should come first
    assert coords[0] == "O19"
    assert sheets[0] == "Cash_Flow"

    # LLM inferred cells
    assert "P17" in coords
    assert "P33" in coords
    assert usage.total_tokens == 60
    assert usage.prompt_tokens == 50
    assert usage.completion_tokens == 10
    assert cost >= 0.0


def test_answer_refiner_module_contract():
    """Verify module definition and schema compliance."""
    module = AnswerRefinerModule()
    contract = module.contract()

    assert contract["type"] == "answer_refiner"
    assert contract["category"] == "Output"
    assert "answer_json" in contract["inputs"]
    assert "refined_answer_json" in contract["outputs"]
    assert "cell_extractor_prompt" in contract["config_fields"]
    assert "max_direct_cells" in contract["config_fields"]


def test_answer_refiner_execution_with_llm_reasoning():
    """Verify end-to-end execution of AnswerRefinerModule with pure LLM spatial reasoning."""
    store = FakeCellStore()
    module = AnswerRefinerModule(
        pgvector_store=store,
        completion_client=FakeReasoningCompletionClient(),
    )

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
        "max_direct_cells": 10,
    }

    result = module.execute(mock_input)

    assert "refined_answer_json" in result
    refined = result["refined_answer_json"]

    assert refined["query_context"]["question_id"] == "QUERY-TEST-1234"
    assert "2025년 금융부문 매출" in refined["refined_answer"]
    assert len(refined["direct_cells"]) == 2
    assert refined["latency_seconds"] >= 0.0
    assert {reference["sheet_name"] for reference in store.cell_references} == {
        "Income_Statement",
        "Balance_Sheet",
    }
    # Accumulated usage: initial (prompt=100, comp=50, total=150)
    #                  + extractor (prompt=50, comp=10, total=60)
    #                  + refiner (prompt=100, comp=40, total=140)
    #                  = prompt=250, completion=100, total=350
    assert refined["api_usage"]["prompt_tokens"] == 250
    assert refined["api_usage"]["completion_tokens"] == 100
    assert refined["api_usage"]["total_tokens"] == 350
    assert refined["estimated_cost_usd"] > 0.0


def test_infer_candidate_cells_raises_on_llm_failure():
    """Verify that LLM completion errors in candidate inference raise ModuleExecutionError."""
    from unittest.mock import MagicMock
    from backend.modules.base import ModuleExecutionError

    mock_client = MagicMock()
    mock_client.complete_with_metadata.side_effect = RuntimeError("API rate limit exceeded")

    module = AnswerRefinerModule(completion_client=mock_client)
    with pytest.raises(ModuleExecutionError, match="LLM 셀 공간 위상 추론 호출 실패"):
        module._infer_candidate_cells(
            question="테스트 질문",
            initial_answer="테스트 답변",
        )


def test_infer_candidate_cells_raises_on_invalid_or_non_array_json():
    """Verify that non-array or invalid JSON responses raise ModuleExecutionError."""
    from unittest.mock import MagicMock
    from backend.modules.base import ModuleExecutionError

    # Non-array JSON (dict instead of list)
    mock_client = MagicMock()
    mock_client.complete_with_metadata.return_value = ChatCompletionResult(
        content='{"cell": "P17"}',
        usage={"total_tokens": 10},
        latency_seconds=0.01,
    )
    module = AnswerRefinerModule(completion_client=mock_client)
    with pytest.raises(ModuleExecutionError, match="JSON 배열을 찾을 수 없습니다|결과가 배열"):
        module._infer_candidate_cells(
            question="테스트 질문",
            initial_answer="테스트 답변",
        )

    # Missing brackets
    mock_client.complete_with_metadata.return_value = ChatCompletionResult(
        content='[ "P17", broken without closing bracket',
        usage={"total_tokens": 10},
        latency_seconds=0.01,
    )
    with pytest.raises(ModuleExecutionError, match="JSON 배열을 찾을 수 없습니다"):
        module._infer_candidate_cells(
            question="테스트 질문",
            initial_answer="테스트 답변",
        )

    # Malformed JSON syntax within brackets
    mock_client.complete_with_metadata.return_value = ChatCompletionResult(
        content='[ "P17", broken ]',
        usage={"total_tokens": 10},
        latency_seconds=0.01,
    )
    with pytest.raises(ModuleExecutionError, match="JSON 파싱 실패"):
        module._infer_candidate_cells(
            question="테스트 질문",
            initial_answer="테스트 답변",
        )


def test_infer_candidate_cells_accepts_valid_empty_array():
    """Verify that a valid empty array response is accepted as zero candidates."""
    from unittest.mock import MagicMock

    mock_client = MagicMock()
    mock_client.complete_with_metadata.return_value = ChatCompletionResult(
        content='[]',
        usage={"prompt_tokens": 20, "completion_tokens": 2, "total_tokens": 22},
        latency_seconds=0.01,
    )
    module = AnswerRefinerModule(completion_client=mock_client)
    candidates, usage, cost = module._infer_candidate_cells(
        question="테스트 질문",
        initial_answer="테스트 답변",
    )
    assert candidates == []
    assert usage.total_tokens == 22
    assert cost >= 0.0


def test_skip_inference_when_target_cells_at_max():
    """Verify that inference is skipped when target_cell_ids count >= max_direct_cells and usage summation succeeds."""
    from unittest.mock import MagicMock

    mock_pgvector = FakeCellStore()

    calls = []
    def mock_complete(model, messages, response_format=None):
        system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
        if "spatial reasoning" in system_msg.lower() or "topology" in system_msg.lower():
            raise Exception("Should not call LLM when skipping inference")
        calls.append(model)
        return ChatCompletionResult(
            content='{"refined_answer": "정제된 답변", "refinement_summary": "수정 요약"}',
            usage={"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
            latency_seconds=0.01,
        )

    mock_client = MagicMock()
    mock_client.complete_with_metadata.side_effect = mock_complete

    module = AnswerRefinerModule(completion_client=mock_client, pgvector_store=mock_pgvector)

    # Initial answer DTO
    initial_answer_dto = AnswerDTO(
        query_context=QueryContextDTO(question_id="q1", question_text="질문 테스트"),
        document_context=DocumentContextDTO(
            file_name="SPG_Company_KeyStats_v4.xlsm",
            workbook_hash="6f4a07f1f3023def767a68ffb8531c7f3867f3f622555aeef2d84d7390c6cae4",
        ),
        model="gpt-5.6-luna",
        answer="초기 답변",
        api_usage=ApiUsageDTO(total_tokens=100, prompt_tokens=80, completion_tokens=20),
        latency_seconds=0.5,
        estimated_cost_usd=0.0001,
    )

    # Provide enough target_cell_ids to reach max_direct_cells
    payload = AnswerRefinerInputDTO(
        answer_json=initial_answer_dto,
        target_cell_ids=["P17", "P33", "Q40"],
    )

    # Execute with max_direct_cells=3 (exactly matching target_cell_ids count)
    result = module.execute(payload.model_dump() | {"max_direct_cells": 3})

    # Verify execution succeeded without calling LLM spatial reasoning inference
    assert result is not None
    assert "refined_answer_json" in result
    assert len(calls) == 1
    refined = result["refined_answer_json"]

    # Verify usage summation succeeded with None normalization
    assert refined["api_usage"]["total_tokens"] == 170
    assert refined["api_usage"]["prompt_tokens"] >= 0

    # Verify that direct cells were fetched from mock with expected candidates
    ref_coords = {r["cell_coord"] if isinstance(r, dict) else r for r in mock_pgvector.cell_references}
    assert ref_coords == {"P17", "P33", "Q40"}
