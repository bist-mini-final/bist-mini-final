"""HTTP presentation for chatbot sessions and workflow-backed turns."""

from __future__ import annotations

from typing import Any

from anyio import to_thread
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from backend.domains.chatbot.application import ChatApiServices, ChatSuggestionService
from backend.domains.chatbot.domain import UnsupportedChatAttachmentError

from .schemas import CreateMessageRequest, CreateSessionRequest, RenameSessionRequest

_UPLOAD_READ_LIMIT = 20 * 1024 * 1024 + 1


def _create_suggestion_router(service: ChatSuggestionService) -> APIRouter:
    router = APIRouter()

    @router.get("/suggestions")
    def list_suggestions() -> dict[str, list[str]]:
        return {"questions": service.refresh_if_due()}

    @router.post("/suggestions/refresh")
    def refresh_suggestions() -> dict[str, list[str]]:
        return {"questions": service.refresh_if_due(force=True)}

    return router


def create_chat_router(
    services: ChatApiServices,
    *,
    prefix: str = "/chat",
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=["Chat"])
    conversations = services.conversations

    @router.get("/sessions")
    def list_sessions(client_id: str = Query(min_length=12, max_length=128)) -> dict[str, Any]:
        return conversations.list_sessions(client_id)

    router.include_router(_create_suggestion_router(services.suggestions))

    @router.post("/sessions", status_code=201)
    def create_session(request: CreateSessionRequest) -> dict[str, Any]:
        return conversations.create_session(request.client_id)

    @router.get("/sessions/{session_id}")
    def get_session(
        session_id: str,
        client_id: str = Query(min_length=12, max_length=128),
    ) -> dict[str, Any]:
        return conversations.require_session(session_id, client_id)

    @router.patch("/sessions/{session_id}")
    def rename_session(session_id: str, request: RenameSessionRequest) -> dict[str, Any]:
        return conversations.rename_session(session_id, request.client_id, request.title)

    @router.delete("/sessions/{session_id}")
    def delete_session(
        session_id: str,
        client_id: str = Query(min_length=12, max_length=128),
    ) -> dict[str, str]:
        return conversations.delete_session(session_id, client_id)

    @router.post("/sessions/{session_id}/attachments", status_code=201)
    async def upload_attachment(
        session_id: str,
        client_id: str = Form(min_length=12, max_length=128),
        file: UploadFile = File(...),
    ) -> dict[str, Any]:
        await to_thread.run_sync(conversations.require_session, session_id, client_id)
        try:
            content = await file.read(_UPLOAD_READ_LIMIT)
            stored = await to_thread.run_sync(
                lambda: services.attachments.save(
                    file_name=file.filename or "",
                    content_type=file.content_type,
                    content=content,
                )
            )
        except UnsupportedChatAttachmentError as error:
            raise HTTPException(status_code=415, detail=error.message) from error
        finally:
            await file.close()
        return await to_thread.run_sync(
            lambda: conversations.create_attachment(
                session_id,
                attachment_id=stored.attachment_id,
                file_name=stored.file_name,
                content_type=stored.content_type,
                file_size=stored.file_size,
                storage_path=stored.storage_path,
                extracted_text=stored.extracted_text,
            )
        )

    @router.post("/sessions/{session_id}/messages", status_code=202)
    def create_message(session_id: str, request: CreateMessageRequest) -> dict[str, Any]:
        return conversations.create_message(
            session_id,
            request.client_id,
            request.content,
            request.attachment_id,
        )

    @router.get("/runs/{run_id}")
    def sync_run(
        run_id: str,
        client_id: str = Query(min_length=12, max_length=128),
    ) -> dict[str, Any]:
        return conversations.sync_run(run_id, client_id)

    return router


__all__ = ["create_chat_router"]
