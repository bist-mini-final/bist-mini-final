from types import SimpleNamespace

from backend.domains.chatbot.application.grounding import finalize_grounded_answer
from backend.domains.chatbot.domain import (
    company_aliases,
    company_identity_answer,
    is_recent_question_request,
    needs_rag,
)


class FakeRunNodeStore:
    def __init__(self, output: object) -> None:
        self.output = output

    def load_node(self, run_id: str, node_id: str) -> SimpleNamespace:
        del run_id, node_id
        return SimpleNamespace(output=self.output)


def test_bistelligence_korean_alias_is_a_registered_company_alias() -> None:
    aliases = company_aliases("Bistelligence Inc. (NASDAQ: BSTL)")

    assert "비스텔리젼스" in aliases
    assert "BSTL" in aliases


def test_recent_question_request_supports_natural_korean_phrasing() -> None:
    assert is_recent_question_request("내가 방금 뭘 물어봤지?")
    assert is_recent_question_request("직전에 무엇을 물어봤어?")


def test_company_identity_answer_corrects_service_name_misunderstanding() -> None:
    answer = company_identity_answer(
        "Bistelligence Inc. (NASDAQ: BSTL)", "서비스를 지칭하는 이름이라고?"
    )

    assert answer is not None
    assert "회사명" in answer
    assert "서비스명이나 일반적인 솔루션명이 아닙니다" in answer


def test_general_financial_term_question_does_not_use_rag() -> None:
    assert not needs_rag("영업이익이 뭐야?", None)
    assert not needs_rag("영업이익의 뜻을 설명해 주세요.", None)


def test_financial_term_question_with_data_request_uses_rag() -> None:
    assert needs_rag("Bistelligence의 2025년 영업이익은 얼마인가요?", None)
    assert needs_rag("영업이익 추이를 차트로 보여 주세요.", {"company_id": "company-1"})


def _structured_evidence(
    *,
    sheet_name: str = "Balance Sheet",
    cell_coord: str = "E50",
    index_id: str = "idx-ibm",
) -> dict[str, object]:
    return {
        "evidence_id": "EVIDENCE-001",
        "index_id": index_id,
        "workbook_hash": "hash-ibm",
        "file_name": "ibm.xlsx",
        "company_name": "IBM",
        "sheet_name": sheet_name,
        "cell_coord": cell_coord,
        "row_header": ["Total Assets"],
        "column_header": ["2025"],
        "cell_value": "151,880",
        "source_text": "Total Assets: 151,880",
    }


def test_rag_answer_without_reader_selected_citations_is_blocked() -> None:
    run = SimpleNamespace(
        nodes={
            "expand-context": SimpleNamespace(
                output={
                    "cells": [
                        {
                            "sheet_name": "Balance Sheet",
                            "cell_coord": "E50",
                            "source_text": "Total Assets: 151,880",
                        }
                    ]
                }
            )
        }
    )

    answer = finalize_grounded_answer("IBM 총자산은 151,880입니다.", [], run)

    assert answer.answer_markdown == "확인 가능한 근거가 부족해 답변할 수 없습니다."
    assert answer.evidence == []


def test_rag_answer_with_only_reader_selected_citations_is_preserved() -> None:
    run = SimpleNamespace(
        nodes={
            "expand-context": SimpleNamespace(
                output={
                    "cells": [
                        {
                            "index_id": "idx-ibm",
                            "workbook_hash": "hash-ibm",
                            "company_name": "IBM",
                            "sheet_name": "Balance Sheet",
                            "cell_coord": "E50",
                            "source_text": "Total Assets: 151,880",
                        },
                        {
                            "sheet_name": "Balance Sheet",
                            "cell_coord": "F50",
                            "source_text": "Total Assets: 160,000",
                        },
                    ]
                }
            )
        }
    )
    answer = finalize_grounded_answer(
        "IBM 총자산은 151,880입니다.",
        [_structured_evidence()],
        run,
    )

    assert answer.answer_markdown == "IBM 총자산은 151,880입니다."
    assert [item.cell_coord for item in answer.evidence] == ["E50"]


def test_rag_answer_with_same_coordinate_but_wrong_index_is_blocked() -> None:
    run = SimpleNamespace(
        nodes={
            "expand-context": SimpleNamespace(
                output={
                    "cells": [
                        {
                            "index_id": "idx-ibm",
                            "workbook_hash": "hash-ibm",
                            "company_name": "IBM",
                            "sheet_name": "Balance Sheet",
                            "cell_coord": "E50",
                            "source_text": "Total Assets: 151,880",
                        }
                    ]
                }
            )
        }
    )

    answer = finalize_grounded_answer(
        "IBM 총자산은 151,880입니다.",
        [_structured_evidence(index_id="idx-other")],
        run,
    )

    assert answer.answer_markdown == "확인 가능한 근거가 부족해 답변할 수 없습니다."
    assert answer.evidence == []


def test_rag_answer_without_concrete_cells_is_blocked() -> None:
    run = SimpleNamespace(nodes={"expand-context": SimpleNamespace(output={"cells": []})})

    answer = finalize_grounded_answer(
        "IBM 총자산은 151,880입니다.",
        [_structured_evidence()],
        run,
    )

    assert answer.answer_markdown == "확인 가능한 근거가 부족해 답변할 수 없습니다."
    assert answer.evidence == []


def test_compacted_chat_run_validates_reader_evidence_against_expanded_context_log() -> None:
    expanded_cells = [
        {
            "index_id": "idx-ibm",
            "workbook_hash": "hash-ibm",
            "company_name": "IBM",
            "sheet_name": "Balance Sheet",
            "cell_coord": f"E{row}",
        }
        for row in range(10, 50)
    ]
    run = SimpleNamespace(id="run-1", nodes={"expand-context": SimpleNamespace(output=None)})
    logs = FakeRunNodeStore({"cells": expanded_cells})

    answer = finalize_grounded_answer(
        "IBM 총자산은 151,880입니다.",
        [_structured_evidence(cell_coord="E49")],
        run,
        run_nodes=logs,
    )

    assert answer.answer_markdown == "IBM 총자산은 151,880입니다."
    assert [item.cell_coord for item in answer.evidence] == ["E49"]


def test_compacted_chat_run_never_reconstructs_reader_grounding_from_fusion() -> None:
    run = SimpleNamespace(id="run-legacy", nodes={"expand-context": SimpleNamespace(output=None)})
    logs = FakeRunNodeStore(None)

    answer = finalize_grounded_answer(
        "IBM 총자산은 151,880입니다.",
        [_structured_evidence()],
        run,
        run_nodes=logs,
    )

    assert answer.answer_markdown == "확인 가능한 근거가 부족해 답변할 수 없습니다."
    assert answer.evidence == []
