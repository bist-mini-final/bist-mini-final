"""HTTP request DTOs for chatbot endpoints."""

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    client_id: str = Field(min_length=12, max_length=128)


class CreateMessageRequest(CreateSessionRequest):
    content: str = Field(min_length=1, max_length=1000)
    attachment_id: str | None = Field(default=None, min_length=12, max_length=64)


class RenameSessionRequest(CreateSessionRequest):
    title: str = Field(min_length=1, max_length=80)


__all__ = ["CreateMessageRequest", "CreateSessionRequest", "RenameSessionRequest"]
