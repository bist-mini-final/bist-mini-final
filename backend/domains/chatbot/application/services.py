"""Application facade injected into the chatbot HTTP presentation."""

from dataclasses import dataclass

from .attachments import ChatAttachmentService
from .conversations import ChatConversationService
from .suggestions import ChatSuggestionService


@dataclass(frozen=True)
class ChatApiServices:
    conversations: ChatConversationService
    suggestions: ChatSuggestionService
    attachments: ChatAttachmentService


__all__ = ["ChatApiServices"]
