"""Compatibility exports for chatbot attachment helpers."""

from backend.domains.chatbot.application import compact_evidence
from backend.domains.chatbot.infrastructure.filesystem import extract_text

__all__ = ["compact_evidence", "extract_text"]
