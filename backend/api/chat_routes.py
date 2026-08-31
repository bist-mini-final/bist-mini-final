"""HTTP presentation for chatbot sessions and workflow-backed turns."""

from __future__ import annotations

from typing import Any

from anyio import to_thread
from fastapi import APIRouter, File, Form, Query, UploadFile
from pydantic import BaseModel, Field

from backend.domains.bi.application import BiApiServices
from backend.domains.chatbot.application import ChatSuggestionService
from backend.domains.chatbot.application.conversations import ChatConversationService
from backend.engine.workflows import (
    RunDispatcher,
    RunStore,
    WorkflowExecutor,
    WorkflowStore,
)
from backend.features.chatbot.attachments import save_upload
from backend.features.chatbot.grounding import EvidenceCellStorePort
from backend.features.chatbot.repository import ChatSessionRepository
from backend.platform.openai.responses import OpenAIResponsesClient
from backend.storage.db_manager import DatabaseManager


class CreateSessionRequest(BaseModel):
    client_id: str = Field(min_length=12, max_length=128)


class CreateMessageRequest(CreateSessionRequest):
    content: str = Field(min_length=1, max_length=1000)
    attachment_id: str | None = Field(default=None, min_length=12, max_length=64)


class RenameSessionRequest(CreateSessionRequest):
    title: str = Field(min_length=1, max_length=80)


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
    *,
    db_manager: DatabaseManager,
    workflow_store: WorkflowStore,
    run_store: RunStore,
    workflow_executor: WorkflowExecutor,
    workflow_dispatcher: RunDispatcher,
    completion_client: OpenAIResponsesClient,
    bi_services: BiApiServices,
    suggestion_service: ChatSuggestionService,
    pgvector_store: EvidenceCellStorePort,
    prefix: str = "/chat",
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=["Chat"])
    conversations = ChatConversationService(
        repository=ChatSessionRepository(db_manager),
        workflow_store=workflow_store,
        run_store=run_store,
        workflow_executor=workflow_executor,
        workflow_dispatcher=workflow_dispatcher,
        completion_client=completion_client,
        bi_services=bi_services,
        execution_logs=db_manager,
        evidence_cells=pgvector_store,
    )

    @router.get("/sessions")
    def list_sessions(client_id: str = Query(min_length=12, max_length=128)) -> dict[str, Any]:
        return conversations.list_sessions(client_id)

    router.include_router(_create_suggestion_router(suggestion_service))

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
        attachment_id, name, content_type, size, storage_path, extracted_text = await save_upload(
            file
        )
        return await to_thread.run_sync(
            lambda: conversations.create_attachment(
                session_id,
                attachment_id=attachment_id,
                file_name=name,
                content_type=content_type,
                file_size=size,
                storage_path=storage_path,
                extracted_text=extracted_text,
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
