from types import SimpleNamespace

from backend.features.chatbot.api_routes import (
    _company_aliases,
    _company_identity_answer,
    _finalize_grounded_answer,
    _is_recent_question_request,
    _needs_rag,
)


def test_bistelligence_korean_alias_is_a_registered_company_alias() -> None:
    aliases = _company_aliases("Bistelligence Inc. (NASDAQ: BSTL)")

    assert "비스텔리젼스" in aliases
    assert "BSTL" in aliases


def test_recent_question_request_supports_natural_korean_phrasing() -> None:
    assert _is_recent_question_request("내가 방금 뭘 물어봤지?")
    assert _is_recent_question_request("직전에 무엇을 물어봤어?")


def test_company_identity_answer_corrects_service_name_misunderstanding() -> None:
    answer = _company_identity_answer("Bistelligence Inc. (NASDAQ: BSTL)", "서비스를 지칭하는 이름이라고?")

    assert answer is not None
    assert "회사명" in answer
    assert "서비스명이나 일반적인 솔루션명이 아닙니다" in answer


def test_general_financial_term_question_does_not_use_rag() -> None:
    assert not _needs_rag("영업이익이 뭐야?", None)
    assert not _needs_rag("영업이익의 뜻을 설명해 주세요.", None)


def test_financial_term_question_with_data_request_uses_rag() -> None:
    assert _needs_rag("Bistelligence의 2025년 영업이익은 얼마인가요?", None)
    assert _needs_rag("영업이익 추이를 차트로 보여 주세요.", {"company_id": "company-1"})


def test_rag_answer_without_citations_gets_verified_evidence_chips() -> None:
    run = SimpleNamespace(nodes={"expand-context": SimpleNamespace(output={"cells": [{
        "sheet_name": "Balance Sheet", "cell_coord": "E50", "source_text": "Total Assets: 151,880",
    }]})})

    answer = _finalize_grounded_answer("IBM 총자산은 151,880입니다.", run)

    assert "**근거**" in answer
    assert "[Sheet: Balance Sheet | Cell: E50]" in answer


def test_rag_answer_without_concrete_cells_is_blocked() -> None:
    run = SimpleNamespace(nodes={"expand-context": SimpleNamespace(output={"cells": []})})

    assert _finalize_grounded_answer("IBM 총자산은 151,880입니다.", run) == "확인 가능한 근거가 부족해 답변할 수 없습니다."
