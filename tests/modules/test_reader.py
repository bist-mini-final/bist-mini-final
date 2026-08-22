from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from backend.providers.llm.chat_completion import ChatCompletionResult
from modules.common.base_module import DocumentContextDTO, QueryContextDTO
from modules.reader.reader import (
    ContextDTO,
    LookupCellMetadataInput,
    ReaderConfigDTO,
    ReaderInputDTO,
    ReaderModule,
    safe_calculate_expression,
)


def test_safe_calculate_expression():
    assert safe_calculate_expression("(350000 - 65670) / 65670 * 100") == "432.9679"
    assert safe_calculate_expression("round(abs(-12.3456), 2)") == "12.35"
    assert safe_calculate_expression("sum(A, B)", {"A": 10, "B": 20}) == "30"


def test_reader_tool_input_bounds():
    with pytest.raises(ValueError):
        LookupCellMetadataInput(cell_coords=[])

    with pytest.raises(ValueError):
        LookupCellMetadataInput(cell_coords=["../../etc/passwd"])


def test_reader_tool_calling_execution():
    mock_llm = MagicMock()
    mock_llm.complete_with_metadata.side_effect = [
        ChatCompletionResult(
            content="",
            usage={"prompt_tokens": 100, "completion_tokens": 20},
            latency_seconds=0.1,
            tool_calls=[
                {
                    "id": "call_123",
                    "type": "function",
                    "function": {
                        "name": "lookup_cell_metadata",
                        "arguments": '{"cell_coords": ["B10"], "sheet_name": "손익계산서", "company_name": "삼성전자"}',
                    },
                }
            ],
        ),
        ChatCompletionResult(
            content="삼성전자의 손익계산서 B10 셀의 정확한 영업이익은 65,670억원입니다. [Sheet: 손익계산서 | Cell: B10]",
            usage={"prompt_tokens": 150, "completion_tokens": 30},
            latency_seconds=0.15,
        ),
    ]

    mock_store = MagicMock()
    mock_store.fetch_cells_by_metadata.return_value = [
        {
            "cell_coord": "B10",
            "sheet_name": "손익계산서",
            "company_name": "삼성전자",
            "cell_value": "65,670억원",
            "row_header": ["영업이익"],
            "column_header": ["2023"],
            "source_text": "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: 65,670억원",
        }
    ]

    reader = ReaderModule(completion_client=mock_llm, pgvector_store=mock_store)
    input_dto = ReaderInputDTO(
        context_json=ContextDTO(
            query_context=QueryContextDTO(question_id="q1", question_text="삼성전자 2023년 영업이익은?"),
            document_context=DocumentContextDTO(
                file_name="samsung.xlsx",
                workbook_hash="hash123",
                company_name="삼성전자",
                sheet_names=["손익계산서"],
            ),
            top_k_used=5,
            adjacent_radius=2,
            context_characters=100,
            context_blocks=["초안 컨텍스트 데이터"],
        )
    )

    res = reader.execute(input_dto, config=ReaderConfigDTO())
    ans = res["answer_json"]["answer"]
    assert "65,670억원" in ans
    assert "[Sheet: 손익계산서 | Cell: B10]" in ans
    assert mock_store.fetch_cells_by_metadata.called


def test_reader_math_tool_calling_execution():
    mock_llm = MagicMock()
    mock_llm.complete_with_metadata.side_effect = [
        ChatCompletionResult(
            content="",
            usage={"prompt_tokens": 100, "completion_tokens": 20},
            latency_seconds=0.1,
            tool_calls=[
                {
                    "id": "call_math_1",
                    "type": "function",
                    "function": {
                        "name": "calculate_math_expression",
                        "arguments": '{"expression": "(350000 - 65670) / 65670 * 100"}',
                    },
                }
            ],
        ),
        ChatCompletionResult(
            content="영업이익 증가율은 432.97% 입니다. [Sheet: 손익계산서 | Cell: E60, F60]",
            usage={"prompt_tokens": 140, "completion_tokens": 25},
            latency_seconds=0.15,
        ),
    ]

    reader = ReaderModule(completion_client=mock_llm)
    input_dto = ReaderInputDTO(
        context_json=ContextDTO(
            query_context=QueryContextDTO(question_id="q2", question_text="영업이익 증가율은?"),
            document_context=DocumentContextDTO(
                file_name="samsung.xlsx",
                workbook_hash="hash123",
                company_name="삼성전자",
                sheet_names=["손익계산서"],
            ),
            top_k_used=5,
            adjacent_radius=2,
            context_characters=100,
            context_blocks=["2023년 영업이익: 65670억, 2024년 영업이익: 350000억"],
        )
    )

    res = reader.execute(input_dto)
    assert "432.97%" in res["answer_json"]["answer"]
