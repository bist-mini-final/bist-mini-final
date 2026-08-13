"""Shared semantic identity DTOs carried across independently executed modules."""

from __future__ import annotations

import hashlib

from pydantic import Field

from .base import ModuleDTO


def question_id_for(question_text: str) -> str:
    """Return the stable content ID used to correlate every query-side DTO."""

    normalized = " ".join(question_text.split())
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16].upper()
    return f"QUERY-{digest}"


class QueryContextDTO(ModuleDTO):
    """Identity and original text of the user query represented by a payload."""

    question_id: str = Field(
        min_length=1,
        description="전체 질의 파이프라인에서 유지되는 원본 질문 ID",
    )
    question_text: str = Field(
        min_length=1,
        description="검색·컨텍스트·답변이 참조하는 사용자의 원문 질문",
    )


class DocumentContextDTO(ModuleDTO):
    """Identity of the source document represented by retrieval-side data."""

    file_name: str = Field(
        min_length=1,
        description="검색 문서와 벡터 인덱스가 만들어진 원본 파일명",
    )
    workbook_hash: str = Field(
        min_length=1,
        description="원본 문서 버전을 식별하는 콘텐츠 해시",
    )
