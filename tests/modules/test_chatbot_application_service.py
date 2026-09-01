from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from backend.domains.chatbot.application.conversations import (
    ChatConversationService,
    ChatNotFoundError,
)


class InMemoryChatRepository:
    def __init__(
        self,
        *,
        session_exists: bool = True,
        attachment: dict[str, Any] | None = None,
    ) -> None:
        self.session_exists = session_exists
        self.attachment = attachment

    def get_session(self, session_id: str, client_id: str) -> dict[str, Any] | None:
        del session_id, client_id
        return {"id": "chat-1", "messages": []} if self.session_exists else None

    def recent_user_messages(self, session_id: str, limit: int = 6) -> list[str]:
        del session_id, limit
        return ["IBM의 매출은 얼마야?"]

    def company_names(self) -> list[str]:
        return []

    def get_attachment(self, session_id: str, attachment_id: str) -> dict[str, Any] | None:
        del session_id, attachment_id
        return self.attachment

    def create_direct_turn(
        self,
        session_id: str,
        content: str,
        answer: str,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        del session_id, content, attachments
        return {"assistant_message": {"content": answer}, "run_id": None, "mode": "direct"}


class RecordingCompletionClient:
    def __init__(self) -> None:
        self.input_items: list[dict[str, Any]] = []

    def create_response(self, **kwargs: Any) -> SimpleNamespace:
        self.input_items = kwargs["input_items"]
        return SimpleNamespace(content="첨부 파일 분석 결과")


def service(
    repository: InMemoryChatRepository,
    completion_client: Any | None = None,
) -> ChatConversationService:
    unused = cast(Any, object())
    return ChatConversationService(
        repository=cast(Any, repository),
        workflow_store=unused,
        run_store=unused,
        workflow_executor=unused,
        workflow_dispatcher=unused,
        completion_client=completion_client or unused,
        bi_catalog=unused,
        execution_logs=unused,
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


def test_attachment_answer_receives_the_complete_flattened_context() -> None:
    tail_evidence = "Total Enterprise Value (TEV) | 35532"
    extracted_text = "[시트: Key_Stats]\n" + ("Filler | 1\n" * 1_200) + tail_evidence
    repository = InMemoryChatRepository(
        attachment={
            "attachment_id": "attachment-00000001",
            "file_name": "financials.xlsx",
            "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "file_size": 10_000,
            "extracted_text": extracted_text,
        }
    )
    completion = RecordingCompletionClient()

    result = service(repository, completion).create_message(
        "chat-1",
        "client-00000001",
        "이 파일의 총기업가치를 분석해봐",
        "attachment-00000001",
    )

    prompt = str(completion.input_items[0]["content"])
    assert len(extracted_text) > 12_000
    assert extracted_text in prompt
    assert tail_evidence in prompt
    assert result["mode"] == "direct"
