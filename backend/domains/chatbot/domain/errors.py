"""Chatbot-specific failures without transport dependencies."""

from backend.shared.domain import ApplicationValidationError, PayloadTooLargeError


class ChatAttachmentValidationError(ApplicationValidationError):
    code = "CHAT_ATTACHMENT_INVALID"


class UnsupportedChatAttachmentError(ChatAttachmentValidationError):
    code = "CHAT_ATTACHMENT_UNSUPPORTED"


class ChatAttachmentTooLargeError(PayloadTooLargeError):
    code = "CHAT_ATTACHMENT_TOO_LARGE"


__all__ = [
    "ChatAttachmentTooLargeError",
    "ChatAttachmentValidationError",
    "UnsupportedChatAttachmentError",
]
