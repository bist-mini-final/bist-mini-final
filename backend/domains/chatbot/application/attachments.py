"""Attachment evidence selection and storage use cases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


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

__all__ = [
    "ChatAttachmentService",
    "ChatAttachmentStoragePort",
    "StoredChatAttachment",
]
