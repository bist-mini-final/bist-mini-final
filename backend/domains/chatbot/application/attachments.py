"""Attachment evidence selection and storage use cases."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

MAX_EVIDENCE_CHARS = 12_000
_FINANCIAL_TERM_ALIASES = {
    "매출": ("revenue", "sales"),
    "영업이익": ("operating income", "operating profit"),
    "순이익": ("net income", "net earnings"),
    "자산": ("assets", "total assets"),
    "부채": ("liabilities", "debt", "total debt"),
    "자본": ("equity", "shareholders"),
    "현금흐름": ("cash flow", "free cash flow"),
    "이익률": ("margin",),
    "주가": ("share price", "price"),
}


@dataclass(frozen=True)
class StoredChatAttachment:
    attachment_id: str
    file_name: str
    content_type: str | None
    file_size: int
    storage_path: str
    extracted_text: str


class ChatAttachmentStoragePort(Protocol):
    def save(
        self,
        *,
        file_name: str,
        content_type: str | None,
        content: bytes,
    ) -> StoredChatAttachment: ...


class ChatAttachmentService:
    """Persist an uploaded attachment through an injected storage adapter."""

    def __init__(self, storage: ChatAttachmentStoragePort) -> None:
        self._storage = storage

    def save(
        self,
        *,
        file_name: str,
        content_type: str | None,
        content: bytes,
    ) -> StoredChatAttachment:
        return self._storage.save(
            file_name=file_name,
            content_type=content_type,
            content=content,
        )


def _question_terms(question: str) -> set[str]:
    terms = {
        term.casefold()
        for term in re.findall(r"[\w가-힣]{2,}", question)
        if term.casefold() not in {"알려줘", "보여줘", "어떻게", "이것", "그것", "파일", "첨부"}
    }
    for korean, aliases in _FINANCIAL_TERM_ALIASES.items():
        if korean in question:
            terms.update(aliases)
    return terms


def _relevant_rows(lines: list[str], terms: set[str]) -> list[str]:
    selected: list[str] = []
    current_sheet = ""
    recent: list[str] = []
    for line in lines:
        if line.startswith("[시트:"):
            current_sheet = line
            recent = []
            continue
        lowered = line.casefold()
        if any(term in lowered for term in terms):
            selected.extend([current_sheet, *recent[-2:], line])
        recent.append(line)
    return selected


def _representative_rows(lines: list[str]) -> list[str]:
    selected: list[str] = []
    sheet_rows: dict[str, int] = {}
    current_sheet = ""
    for line in lines:
        if line.startswith("[시트:"):
            current_sheet = line
            sheet_rows.setdefault(current_sheet, 0)
            continue
        if current_sheet and sheet_rows[current_sheet] < 4:
            selected.extend([current_sheet, line])
            sheet_rows[current_sheet] += 1
    return selected


def compact_evidence(question: str, extracted_text: str) -> str:
    """Select question-relevant spreadsheet rows before model invocation."""
    lines = [line.strip() for line in extracted_text.splitlines() if line.strip()]
    selected = _relevant_rows(lines, _question_terms(question))
    if not selected:
        selected = _representative_rows(lines)
    result = "\n".join(dict.fromkeys(selected))
    if len(result) > MAX_EVIDENCE_CHARS:
        result = result[:MAX_EVIDENCE_CHARS] + "\n[질문 관련 근거가 길어 일부만 사용했습니다.]"
    return result or extracted_text[:MAX_EVIDENCE_CHARS]


__all__ = [
    "ChatAttachmentService",
    "ChatAttachmentStoragePort",
    "StoredChatAttachment",
    "compact_evidence",
]
