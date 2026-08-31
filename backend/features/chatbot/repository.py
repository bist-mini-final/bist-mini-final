"""Compatibility export for chatbot session persistence."""

from backend.domains.chatbot.infrastructure.postgres import ChatSessionRepository

__all__ = ["ChatSessionRepository"]
