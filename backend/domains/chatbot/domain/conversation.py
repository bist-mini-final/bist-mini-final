from __future__ import annotations

import re

_RAG_TERMS = (
    "매출",
    "영업이익",
    "순이익",
    "자산",
    "부채",
    "자본",
    "현금흐름",
    "재무",
    "실적",
    "eps",
    "dps",
    "수치",
    "얼마",
    "몇",
    "분기",
    "연도",
)
_EXPLANATION_TERMS = (
    "뜻",
    "의미",
    "정의",
    "란",
    "무엇",
    "설명",
    "뭐야",
    "뭐예요",
    "뭔가요",
    "뭔지",
    "무엇인가요",
    "무엇이에요",
)
_DATA_REQUEST_TERMS = (
    "얼마",
    "몇",
    "20",
    "최신",
    "실적",
    "수치",
    "금액",
    "분기",
    "연도",
    "작년",
    "올해",
)
_RECENT_QUESTION_PATTERNS = (
    "방금 뭘 물어봤",
    "방금 무엇을 물어봤",
    "직전에 뭘 물어봤",
    "직전에 무엇을 물어봤",
    "내가 뭐 물어봤",
)
_COMPANY_ALIASES = {
    "bistelligence": ("비스텔리젼스", "비스텔리전스"),
}


def company_aliases(name: str) -> tuple[str, ...]:
    """Return catalog, ticker, and supported Korean aliases for a company."""
    base_name = name.split("(", 1)[0].strip()
    tickers = re.findall(r"\b[A-Z]{2,8}\b", name)
    normalized_name = base_name.casefold()
    aliases = next(
        (values for key, values in _COMPANY_ALIASES.items() if normalized_name.startswith(key)),
        (),
    )
    return tuple(dict.fromkeys((name, base_name, *tickers, *aliases)))


def is_recent_question_request(question: str) -> bool:
    normalized = re.sub(r"\s+", "", question)
    return any(re.sub(r"\s+", "", pattern) in normalized for pattern in _RECENT_QUESTION_PATTERNS)


def company_identity_answer(company: str, question: str) -> str | None:
    """Answer short company-name confirmation and correction questions deterministically."""
    lowered = question.casefold()
    if not any(
        term in lowered for term in ("알아", "회사", "회사명", "서비스", "브랜드명", "이름")
    ):
        return None
    return (
        f"네. 제공된 데이터 기준으로 **{company}**는 분석 대상 회사명입니다. "
        "서비스명이나 일반적인 솔루션명이 아닙니다."
    )


def needs_rag(question: str, visualization: dict[str, str] | None) -> bool:
    """Route only requests for stored company data to the RAG workflow."""
    lowered = question.casefold()
    if visualization is not None:
        return True
    if any(term in lowered for term in _EXPLANATION_TERMS) and not any(
        marker in lowered for marker in _DATA_REQUEST_TERMS
    ):
        return False
    return any(term in lowered for term in _RAG_TERMS)


__all__ = [
    "company_aliases",
    "company_identity_answer",
    "is_recent_question_request",
    "needs_rag",
]
