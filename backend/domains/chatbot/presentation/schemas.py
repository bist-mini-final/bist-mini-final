"""HTTP request and response DTOs for chatbot endpoints."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.shared.application.cell_evidence import CellEvidenceDTO


class CreateSessionRequest(BaseModel):
    client_id: str = Field(min_length=12, max_length=128)


class CreateMessageRequest(CreateSessionRequest):
    content: str = Field(min_length=1, max_length=1000)
    attachment_id: str | None = Field(default=None, min_length=12, max_length=64)


class RenameSessionRequest(CreateSessionRequest):
    title: str = Field(min_length=1, max_length=80)


class ChatAttachmentResponse(BaseModel):
    id: str
    name: str
    content_type: str | None
    size: int = Field(ge=0)
    created_at: datetime | None = None


class ChatVisualizationResponse(BaseModel):
    company_id: str
    card_id: str


class ChatMessageResponse(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    status: Literal["processing", "completed", "failed"]
    run_id: str | None
    visualization: ChatVisualizationResponse | None
    evidence: list[CellEvidenceDTO] = Field(default_factory=list)
    attachments: list[ChatAttachmentResponse] = Field(default_factory=list)
    created_at: datetime


class ChatSessionResponse(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[ChatMessageResponse] = Field(default_factory=list)


class ChatSessionListResponse(BaseModel):
    sessions: list[ChatSessionResponse]


class ChatMessageCreatedResponse(BaseModel):
    assistant_message: ChatMessageResponse
    run_id: str | None
    mode: Literal["direct", "rag"]


class ChatRunSyncResponse(BaseModel):
    run: Any
    message: ChatMessageResponse | None


class ChatSuggestionListResponse(BaseModel):
    questions: list[str]


class DeleteSessionResponse(BaseModel):
    deleted: str


__all__ = [
    "ChatAttachmentResponse",
    "ChatMessageCreatedResponse",
    "ChatMessageResponse",
    "ChatRunSyncResponse",
    "ChatSessionListResponse",
    "ChatSessionResponse",
    "ChatSuggestionListResponse",
    "ChatVisualizationResponse",
    "CreateMessageRequest",
    "CreateSessionRequest",
    "DeleteSessionResponse",
    "RenameSessionRequest",
]
