"""Compatibility export for the chatbot PostgreSQL suggestion adapter."""

from backend.domains.chatbot.infrastructure.postgres import ChatSuggestionRepository

__all__ = ["ChatSuggestionRepository"]
