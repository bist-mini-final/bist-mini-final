from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.platform.openai.responses import OpenAIResponseResult
from modules.common.base_module import DocumentContextDTO, QueryContextDTO
from modules.reader.reader import ContextDTO as ContextDTOModel
from modules.reader.reader import (
    LookupCellMetadataInput,
    ReaderConfigDTO,
    ReaderInputDTO,
    ReaderModule,
    safe_calculate_expression,
)


def ContextDTO(**data: Any) -> ContextDTOModel:
    """Let Pydantic validate mapping-shaped fixtures without weakening production types."""
    return ContextDTOModel.model_validate(data)


def structured_answer(answer_markdown: str, evidence_ids: list[str]) -> str:
    return json.dumps(
        {"answer_markdown": answer_markdown, "evidence_ids": evidence_ids},
        ensure_ascii=False,
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
    mock_llm.create_response.side_effect = [
        OpenAIResponseResult(
            response_id="resp_lookup_call",
            content="",
            usage={"prompt_tokens": 100, "completion_tokens": 20},
            latency_seconds=0.1,
            function_calls=(
                {
                    "call_id": "call_123",
                    "name": "lookup_cell_metadata",
                    "arguments": '{"cell_coords": ["B10"], "sheet_name": "손익계산서", "company_name": "삼성전자"}',
                },
            ),
        ),
        OpenAIResponseResult(
            response_id="resp_lookup_answer",
            content=structured_answer(
                "삼성전자의 손익계산서 B10 셀의 정확한 영업이익은 65,670억원입니다.",
                ["EVIDENCE-001"],
            ),
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
        },
        {
            "cell_coord": "C10",
            "sheet_name": "손익계산서",
            "company_name": "삼성전자",
            "cell_value": "?",
            "row_header": ["영업이익"],
            "column_header": ["2024"],
            "source_text": "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2024 | Cell Value: ?",
        },
    ]

    reader = ReaderModule(completion_client=mock_llm, pgvector_store=mock_store)
    input_dto = ReaderInputDTO(
        context_json=ContextDTO(
            query_context=QueryContextDTO(
                question_id="q1", question_text="삼성전자 2023년 영업이익은?"
            ),
            document_context=DocumentContextDTO(
                file_name="samsung.xlsx",
                workbook_hash="hash123",
                company_name="삼성전자",
                sheet_names=["손익계산서"],
            ),
            items=["초안 컨텍스트 데이터"],
            cells=[
                {
                    "cell_coord": "B10",
                    "sheet_name": "손익계산서",
                    "source_text": "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: 65,670억원",
                }
            ],
        )
    )

    res = reader.execute(input_dto, config=ReaderConfigDTO())
    ans = res["answer_json"]["answer_markdown"]
    assert "65,670억원" in ans
    assert res["answer_json"]["evidence"][0]["cell_coord"] == "B10"
    assert mock_store.fetch_cells_by_metadata.called
    first_call, continuation = mock_llm.create_response.call_args_list
    assert first_call.kwargs["text_format"]["name"] == "ReaderEvidenceSelectionDTO"
    assert first_call.kwargs["text_format"]["strict"] is True
    function_tool = first_call.kwargs["tools"][0]
    assert function_tool["type"] == "function"
    assert function_tool["strict"] is True
    assert function_tool["parameters"]["additionalProperties"] is False
    assert continuation.kwargs["previous_response_id"] == "resp_lookup_call"
    assert continuation.kwargs["input_items"][0]["type"] == "function_call_output"
    assert continuation.kwargs["input_items"][0]["call_id"] == "call_123"
    assert "Cell Value: ?" not in continuation.kwargs["input_items"][0]["output"]


def test_reader_math_tool_calling_execution():
    mock_llm = MagicMock()
    mock_llm.create_response.side_effect = [
        OpenAIResponseResult(
            response_id="resp_math_call",
            content="",
            usage={"prompt_tokens": 100, "completion_tokens": 20},
            latency_seconds=0.1,
            function_calls=(
                {
                    "call_id": "call_math_1",
                    "name": "calculate_math_expression",
                    "arguments": '{"expression": "(350000 - 65670) / 65670 * 100"}',
                },
            ),
        ),
        OpenAIResponseResult(
            response_id="resp_math_answer",
            content=structured_answer(
                "영업이익 증가율은 432.97% 입니다.",
                ["EVIDENCE-001", "EVIDENCE-002"],
            ),
            usage={"prompt_tokens": 140, "completion_tokens": 25},
            latency_seconds=0.15,
        ),
    ]

    reader = ReaderModule(
        completion_client=mock_llm,
        pgvector_store=MagicMock(),
    )
    input_dto = ReaderInputDTO(
        context_json=ContextDTO(
            query_context=QueryContextDTO(question_id="q2", question_text="영업이익 증가율은?"),
            document_context=DocumentContextDTO(
                file_name="samsung.xlsx",
                workbook_hash="hash123",
                company_name="삼성전자",
                sheet_names=["손익계산서"],
            ),
            items=["2023년 영업이익: 65670억, 2024년 영업이익: 350000억"],
            cells=[
                {
                    "cell_coord": "E60",
                    "sheet_name": "손익계산서",
                    "source_text": "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: 65670억",
                },
                {
                    "cell_coord": "F60",
                    "sheet_name": "손익계산서",
                    "source_text": "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2024 | Cell Value: 350000억",
                },
            ],
        )
    )

    res = reader.execute(input_dto)
    assert "432.97%" in res["answer_json"]["answer_markdown"]
    assert [item["cell_coord"] for item in res["answer_json"]["evidence"]] == [
        "E60",
        "F60",
    ]


def test_reader_native_async_response_path() -> None:
    mock_llm = MagicMock()
    mock_llm.create_response_async = AsyncMock(
        return_value=OpenAIResponseResult(
            response_id="resp_async_reader",
            content=structured_answer("비동기 답변입니다.", ["EVIDENCE-001"]),
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            latency_seconds=0.05,
        )
    )
    reader = ReaderModule(completion_client=mock_llm, pgvector_store=MagicMock())
    input_dto = ReaderInputDTO(
        context_json=ContextDTO(
            query_context=QueryContextDTO(question_id="q3", question_text="답변해줘"),
            document_context=DocumentContextDTO(
                file_name="sample.xlsx",
                workbook_hash="hash-async",
                sheet_names=["손익계산서"],
            ),
            items=["근거"],
            cells=[
                {
                    "cell_coord": "B10",
                    "sheet_name": "손익계산서",
                    "source_text": "Company: 삼성전자 | Sheet: 손익계산서 | Row Header: 영업이익 | Column Header: 2023 | Cell Value: 65670",
                }
            ],
        )
    )

    result = asyncio.run(reader.run_async(input_dto))

    assert result["answer_json"]["answer_markdown"].startswith("비동기 답변")
    mock_llm.create_response_async.assert_awaited_once()


def test_reader_native_async_cell_lookup_tool_path() -> None:
    mock_llm = MagicMock()
    mock_llm.create_response_async = AsyncMock(
        side_effect=[
            OpenAIResponseResult(
                response_id="resp_async_lookup",
                content="",
                usage={"prompt_tokens": 10, "completion_tokens": 5},
                latency_seconds=0.02,
                function_calls=(
                    {
                        "call_id": "call_async_lookup",
                        "name": "lookup_cell_metadata",
                        "arguments": '{"cell_coords": ["B10"]}',
                    },
                ),
            ),
            OpenAIResponseResult(
                response_id="resp_async_answer",
                content=structured_answer(
                    "비동기 조회 결과는 70,000억원입니다.",
                    ["EVIDENCE-001"],
                ),
                usage={"prompt_tokens": 20, "completion_tokens": 8},
                latency_seconds=0.03,
            ),
        ]
    )
    store = MagicMock()
    store.fetch_cells_by_metadata_async = AsyncMock(
        return_value=[
            {
                "cell_coord": "B10",
                "sheet_name": "손익계산서",
                "company_name": "삼성전자",
                "cell_value": "70,000억원",
                "row_header": ["영업이익"],
                "column_header": ["2024"],
                "source_text": "영업이익 | 2024 | Cell Value: 70,000억원",
            }
        ]
    )
    reader = ReaderModule(completion_client=mock_llm, pgvector_store=store)
    input_dto = ReaderInputDTO(
        context_json=ContextDTO(
            query_context=QueryContextDTO(question_id="q4", question_text="영업이익은?"),
            document_context=DocumentContextDTO(
                file_name="sample.xlsx",
                workbook_hash="hash-async",
                company_name="삼성전자",
                sheet_names=["손익계산서"],
            ),
            items=["근거"],
            cells=[
                {
                    "cell_coord": "B10",
                    "sheet_name": "손익계산서",
                    "source_text": "영업이익 | 2024 | Cell Value: 70,000억원",
                }
            ],
        )
    )

    result = asyncio.run(reader.run_async(input_dto))

    assert "70,000억원" in result["answer_json"]["answer_markdown"]
    store.fetch_cells_by_metadata_async.assert_awaited_once()
    store.fetch_cells_by_metadata.assert_not_called()


def test_reader_rejects_numeric_answer_when_no_verifiable_cells_exist():
    mock_llm = MagicMock()
    reader = ReaderModule(completion_client=mock_llm, pgvector_store=MagicMock())
    input_dto = ReaderInputDTO(
        context_json=ContextDTO(
            query_context=QueryContextDTO(
                question_id="q3", question_text="IBM 총자산은 얼마인가요?"
            ),
            document_context=DocumentContextDTO(file_name="ibm.xlsx", workbook_hash="hash123"),
            items=["IBM 총자산: 151,880"],
        )
    )

    result = reader.execute(input_dto)

    assert result["answer_json"]["answer_markdown"] == "확인 가능한 근거가 부족해 답변할 수 없습니다."
    assert result["answer_json"]["evidence"] == []
    assert not mock_llm.create_response.called


def test_reader_rejects_header_only_cells_as_evidence() -> None:
    mock_llm = MagicMock()
    reader = ReaderModule(completion_client=mock_llm, pgvector_store=MagicMock())
    input_dto = ReaderInputDTO(
        context_json=ContextDTO(
            query_context=QueryContextDTO(
                question_id="q-header-only", question_text="IBM 2024 총매출은?"
            ),
            document_context=DocumentContextDTO(file_name="ibm.xlsx", workbook_hash="hash123"),
            items=["[No context blocks available]"],
            cells=[
                {
                    "cell_coord": "O201",
                    "sheet_name": "Balance_Sheet",
                    "source_text": (
                        "Company: IBM | Sheet: Balance_Sheet | Row Header: Period Date | "
                        "Column Header: 2024-12-31 | Cell Value: ?"
                    ),
                }
            ],
        )
    )

    result = reader.execute(input_dto)

    assert result["answer_json"]["answer_markdown"] == "확인 가능한 근거가 부족해 답변할 수 없습니다."
    assert result["answer_json"]["evidence"] == []
    assert not mock_llm.create_response.called


def test_reader_prompt_contains_only_value_bearing_cells() -> None:
    mock_llm = MagicMock()
    mock_llm.create_response.return_value = OpenAIResponseResult(
        response_id="resp-value-boundary",
        content=structured_answer(
            "IBM의 2024년 매출은 62,753입니다.",
            ["EVIDENCE-001"],
        ),
        usage={"prompt_tokens": 50, "completion_tokens": 15},
        latency_seconds=0.1,
    )
    reader = ReaderModule(completion_client=mock_llm, pgvector_store=MagicMock())
    valid = (
        "Company: IBM | Sheet: Income_Statement | Row Header: Total Revenue | "
        "Column Header: 2024-12-31 | Cell Value: 62753"
    )
    placeholder = (
        "Company: IBM | Sheet: Balance_Sheet | Row Header: Period Date | "
        "Column Header: 2024-12-31 | Cell Value: ?"
    )
    result = reader.execute(
        ReaderInputDTO(
            context_json=ContextDTO(
                query_context=QueryContextDTO(
                    question_id="q-reader-boundary",
                    question_text="IBM 2024 총매출은?",
                ),
                document_context=DocumentContextDTO(
                    file_name="ibm.xlsx",
                    workbook_hash="hash123",
                ),
                items=[placeholder, "raw retrieval hint must not reach Reader", valid],
                cells=[
                    {
                        "cell_coord": "O201",
                        "sheet_name": "Balance_Sheet",
                        "source_text": placeholder,
                    },
                    {
                        "cell_coord": "O23",
                        "sheet_name": "Income_Statement",
                        "source_text": valid,
                    },
                ],
            )
        )
    )

    prompt = mock_llm.create_response.call_args.kwargs["input_items"][0]["content"]
    assert valid in prompt
    assert placeholder not in prompt
    assert "raw retrieval hint must not reach Reader" not in prompt
    system_prompt = mock_llm.create_response.call_args.kwargs["instructions"]
    assert "후보 전체를 선택하지 마십시오" in system_prompt
    assert "출처는 오직 `evidence_ids` 배열" in system_prompt
    assert "62,753" in result["answer_json"]["answer_markdown"]
    assert [item["cell_coord"] for item in result["answer_json"]["evidence"]] == ["O23"]


def test_reader_rejects_answer_with_an_unsupported_cell_citation():
    mock_llm = MagicMock()
    mock_llm.create_response.return_value = OpenAIResponseResult(
        response_id="resp_answer",
        content=structured_answer(
            "IBM 총자산은 151,880입니다.",
            ["EVIDENCE-999"],
        ),
        usage={"prompt_tokens": 100, "completion_tokens": 20},
        latency_seconds=0.1,
    )
    reader = ReaderModule(completion_client=mock_llm, pgvector_store=MagicMock())
    input_dto = ReaderInputDTO(
        context_json=ContextDTO(
            query_context=QueryContextDTO(
                question_id="q4", question_text="IBM 총자산은 얼마인가요?"
            ),
            document_context=DocumentContextDTO(file_name="ibm.xlsx", workbook_hash="hash123"),
            items=["IBM 총자산: 151,880"],
            cells=[
                {
                    "cell_coord": "E50",
                    "sheet_name": "Balance Sheet",
                    "source_text": "Company: IBM | Sheet: Balance Sheet | Row Header: Total Assets | Column Header: 2025 | Cell Value: 151880",
                }
            ],
        )
    )

    result = reader.execute(input_dto)

    assert result["answer_json"]["answer_markdown"] == "확인 가능한 근거가 부족해 답변할 수 없습니다."
    assert result["answer_json"]["evidence"] == []


def test_reader_rejects_answer_when_model_omits_selected_citations():
    mock_llm = MagicMock()
    mock_llm.create_response.return_value = OpenAIResponseResult(
        response_id="resp_answer",
        content=structured_answer("IBM 총자산은 151,880입니다.", []),
        usage={"prompt_tokens": 100, "completion_tokens": 20},
        latency_seconds=0.1,
    )
    reader = ReaderModule(completion_client=mock_llm, pgvector_store=MagicMock())
    input_dto = ReaderInputDTO(
        context_json=ContextDTO(
            query_context=QueryContextDTO(
                question_id="q5", question_text="IBM 총자산은 얼마인가요?"
            ),
            document_context=DocumentContextDTO(file_name="ibm.xlsx", workbook_hash="hash123"),
            items=["IBM 총자산: 151,880"],
            cells=[
                {
                    "cell_coord": "E50",
                    "sheet_name": "Balance Sheet",
                    "source_text": "Company: IBM | Sheet: Balance Sheet | Row Header: Total Assets | Column Header: 2025 | Cell Value: 151880",
                }
            ],
        )
    )

    result = reader.execute(input_dto)

    assert result["answer_json"]["answer_markdown"] == "확인 가능한 근거가 부족해 답변할 수 없습니다."
    assert result["answer_json"]["evidence"] == []


def test_reader_returns_only_model_selected_structured_evidence():
    mock_llm = MagicMock()
    mock_llm.create_response.return_value = OpenAIResponseResult(
        response_id="resp_selected_evidence",
        content=structured_answer(
            "AmeSoft의 2024년 총매출(Total Revenue)은 **12,636**입니다.",
            ["EVIDENCE-001"],
        ),
        usage={"prompt_tokens": 100, "completion_tokens": 20},
        latency_seconds=0.1,
    )
    reader = ReaderModule(completion_client=mock_llm, pgvector_store=MagicMock())
    sources = [
        (
            "O23",
            "Company: AmeSoft | Sheet: Income Statement | Row Header: Total Revenue | "
            "Column Header: FY2024 | Cell Value: 12,636",
        ),
        (
            "E16",
            "Company: AmeSoft | Sheet: Income Statement | Row Header: Revenue Growth | "
            "Column Header: FY2021 | Cell Value: 9.1%",
        ),
        (
            "F16",
            "Company: AmeSoft | Sheet: Income Statement | Row Header: Revenue Growth | "
            "Column Header: FY2022 | Cell Value: 10.2%",
        ),
    ]
    result = reader.execute(
        ReaderInputDTO(
            context_json=ContextDTO(
                query_context=QueryContextDTO(
                    question_id="q-selected-evidence",
                    question_text="AmeSoft 2024년 총매출은?",
                ),
                document_context=DocumentContextDTO(
                    file_name="amesoft.xlsm",
                    workbook_hash="hash-amesoft",
                ),
                cells=[
                    {"cell_coord": coord, "sheet_name": "Income Statement", "source_text": source}
                    for coord, source in sources
                ],
            )
        )
    )

    answer = result["answer_json"]["answer_markdown"]
    assert "Income Statement O23" not in answer
    assert "**근거**" not in answer
    assert [item["cell_coord"] for item in result["answer_json"]["evidence"]] == ["O23"]


def test_reader_preserves_verified_ids_when_model_also_returns_unsupported_ids() -> None:
    mock_llm = MagicMock()
    mock_llm.create_response.return_value = OpenAIResponseResult(
        response_id="resp-mixed-evidence-ids",
        content=structured_answer(
            "Nexora Labs의 총자산은 10,283이고 총부채는 3,496입니다.",
            ["evidence_1", "EVIDENCE-002", "EVIDENCE-999"],
        ),
        usage={"prompt_tokens": 100, "completion_tokens": 20},
        latency_seconds=0.1,
    )
    reader = ReaderModule(completion_client=mock_llm, pgvector_store=MagicMock())
    result = reader.execute(
        ReaderInputDTO(
            context_json=ContextDTO(
                query_context=QueryContextDTO(
                    question_id="q-mixed-evidence-ids",
                    question_text="Nexora Labs의 총자산과 총부채는?",
                ),
                document_context=DocumentContextDTO(
                    index_id="idx-nexora",
                    file_name="nexora.xlsx",
                    workbook_hash="hash-nexora",
                    company_name="Nexora Labs",
                    sheet_names=["Balance_Sheet"],
                ),
                cells=[
                    {
                        "index_id": "idx-nexora",
                        "cell_coord": "Q50",
                        "cell_value": "10282.93",
                        "sheet_name": "Balance_Sheet",
                        "company_name": "Nexora Labs",
                        "source_text": (
                            "Company: Nexora Labs | Sheet: Balance_Sheet | "
                            "Row Header: Total Assets | Column Header: 2025-12-31 | "
                            "Cell Value: 10282.93"
                        ),
                    },
                    {
                        "index_id": "idx-nexora",
                        "cell_coord": "Q74",
                        "cell_value": "3496.20",
                        "sheet_name": "Balance_Sheet",
                        "company_name": "Nexora Labs",
                        "source_text": (
                            "Company: Nexora Labs | Sheet: Balance_Sheet | "
                            "Row Header: Total Liabilities | Column Header: 2025-12-31 | "
                            "Cell Value: 3496.20"
                        ),
                    },
                ],
            )
        )
    )

    assert "총자산" in result["answer_json"]["answer_markdown"]
    assert [item["evidence_id"] for item in result["answer_json"]["evidence"]] == [
        "EVIDENCE-001",
        "EVIDENCE-002",
    ]


def test_reader_still_rejects_when_every_selected_id_is_unsupported() -> None:
    mock_llm = MagicMock()
    mock_llm.create_response.return_value = OpenAIResponseResult(
        response_id="resp-unsupported-evidence-ids",
        content=structured_answer("근거 없는 답변", ["EVIDENCE-999"]),
        usage={},
        latency_seconds=0.1,
    )
    reader = ReaderModule(completion_client=mock_llm, pgvector_store=MagicMock())
    result = reader.execute(
        ReaderInputDTO(
            context_json=ContextDTO(
                query_context=QueryContextDTO(
                    question_id="q-unsupported-evidence-ids",
                    question_text="Nexora Labs의 총자산은?",
                ),
                document_context=DocumentContextDTO(
                    file_name="nexora.xlsx",
                    workbook_hash="hash-nexora",
                ),
                cells=[
                    {
                        "cell_coord": "Q50",
                        "sheet_name": "Balance_Sheet",
                        "source_text": (
                            "Company: Nexora Labs | Sheet: Balance_Sheet | "
                            "Row Header: Total Assets | Column Header: 2025-12-31 | "
                            "Cell Value: 10282.93"
                        ),
                    }
                ],
            )
        )
    )

    assert result["answer_json"]["answer_markdown"] == (
        "확인 가능한 근거가 부족해 답변할 수 없습니다."
    )
    assert result["answer_json"]["evidence"] == []
