from __future__ import annotations

from typing import Any, cast

import pytest

from backend.domains.chatbot.application.conversations import (
    ChatConversationService,
    ChatNotFoundError,
)


class InMemoryChatRepository:
    def __init__(self, *, session_exists: bool = True) -> None:
        self.session_exists = session_exists

    def get_session(self, session_id: str, client_id: str) -> dict[str, Any] | None:
        del session_id, client_id
        return {"id": "chat-1", "messages": []} if self.session_exists else None

    def recent_user_messages(self, session_id: str, limit: int = 6) -> list[str]:
        del session_id, limit
        return ["IBM의 매출은 얼마야?"]

    def company_names(self) -> list[str]:
        return []

    def get_attachment(self, session_id: str, attachment_id: str) -> None:
        del session_id, attachment_id

    def create_direct_turn(
        self,
        session_id: str,
        content: str,
        answer: str,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        del session_id, content, attachments
        return {"assistant_message": {"content": answer}, "run_id": None, "mode": "direct"}


def service(repository: InMemoryChatRepository) -> ChatConversationService:
    unused = cast(Any, object())
    return ChatConversationService(
        repository=cast(Any, repository),
        workflow_store=unused,
        run_store=unused,
        workflow_executor=unused,
        workflow_dispatcher=unused,
        completion_client=unused,
        bi_catalog=unused,
        execution_logs=unused,
        evidence_cells=unused,
    )


def test_require_session_raises_application_not_found_error() -> None:
    conversations = service(InMemoryChatRepository(session_exists=False))

    with pytest.raises(ChatNotFoundError, match="대화 세션"):
        conversations.require_session("chat-missing", "client-00000001")


def test_recent_question_is_answered_without_llm_or_workflow() -> None:
    conversations = service(InMemoryChatRepository())

    result = conversations.create_message(
        "chat-1",
        "client-00000001",
        "내가 방금 뭘 물어봤지?",
    )

    assert result["mode"] == "direct"
    assert "IBM의 매출은 얼마야?" in result["assistant_message"]["content"]
