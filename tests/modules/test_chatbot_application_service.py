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
        companies: list[str] | None = None,
    ) -> None:
        self.session_exists = session_exists
        self.attachment = attachment
        self.companies = companies or []
        self.created_turn: dict[str, Any] | None = None
        self.completed_turns: list[dict[str, Any]] = []

    def get_session(self, session_id: str, client_id: str) -> dict[str, Any] | None:
        del session_id, client_id
        return {"id": "chat-1", "messages": []} if self.session_exists else None

    def recent_user_messages(self, session_id: str, limit: int = 6) -> list[str]:
        del session_id, limit
        return ["IBM의 매출은 얼마야?"]

    def company_names(self) -> list[str]:
        return self.companies

    def get_attachment(self, session_id: str, attachment_id: str) -> dict[str, Any] | None:
        del session_id, attachment_id
        return self.attachment

    def get_attachment_for_run(self, run_id: str) -> dict[str, Any] | None:
        del run_id
        return self.attachment

    def owns_run(self, run_id: str, client_id: str) -> bool:
        del run_id, client_id
        return True

    def session_id_for_run(self, run_id: str) -> str:
        del run_id
        return "chat-1"

    def complete_turn(self, run_id: str, status: str, content: str, **kwargs: Any) -> dict[str, Any]:
        completed = {"run_id": run_id, "status": status, "content": content, **kwargs}
        self.completed_turns.append(completed)
        return completed

    def create_turn(
        self,
        session_id: str,
        content: str,
        run_id: str,
        visualization: dict[str, str] | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self.created_turn = {
            "session_id": session_id,
            "content": content,
            "run_id": run_id,
            "visualization": visualization,
            "attachments": attachments,
        }
        return {"assistant_message": {"content": ""}, "run_id": run_id, "mode": "rag"}

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


class RecordingWorkflowExecutor:
    def __init__(self) -> None:
        self.request: Any | None = None

    def create_run(self, workflow: Any, request: Any) -> SimpleNamespace:
        del workflow
        self.request = request
        return SimpleNamespace(id="run-combined")


class RecordingWorkflowDispatcher:
    def __init__(self) -> None:
        self.run_ids: list[str] = []

    def submit(self, run_id: str, *, resume_failed: bool = False) -> bool:
        del resume_failed
        self.run_ids.append(run_id)
        return True


class EmptyBiCatalog:
    def list_companies(self) -> tuple[()]:
        return ()


def service(
    repository: InMemoryChatRepository,
    completion_client: Any | None = None,
    *,
    run_store: Any | None = None,
    workflow_executor: Any | None = None,
    workflow_dispatcher: Any | None = None,
) -> ChatConversationService:
    unused = cast(Any, object())
    return ChatConversationService(
        repository=cast(Any, repository),
        workflow_store=cast(Any, SimpleNamespace(load=lambda _workflow_id: object())),
        run_store=run_store or unused,
        workflow_executor=workflow_executor or unused,
        workflow_dispatcher=workflow_dispatcher or unused,
        completion_client=completion_client or unused,
        bi_catalog=cast(Any, EmptyBiCatalog()),
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


def test_attachment_and_stored_company_request_runs_rag_with_attachment_binding() -> None:
    attachment = {
        "attachment_id": "attachment-00000001",
        "file_name": "SPG_Company_KeyStats_10_orbixa_networks.xlsm",
        "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "file_size": 10_000,
        "extracted_text": "[시트: Income Statement]\nTotal Revenue | 2025 | 100",
    }
    repository = InMemoryChatRepository(
        attachment=attachment,
        companies=["Nexora Labs"],
    )
    executor = RecordingWorkflowExecutor()
    dispatcher = RecordingWorkflowDispatcher()

    result = service(
        repository,
        workflow_executor=executor,
        workflow_dispatcher=dispatcher,
    ).create_message(
        "chat-1",
        "client-00000001",
        "Nexora Labs와 Orbixa의 최근 연도 매출과 영업이익을 비교해줘",
        "attachment-00000001",
    )

    assert result["mode"] == "rag"
    assert dispatcher.run_ids == ["run-combined"]
    assert executor.request is not None
    assert "Nexora Labs" in executor.request.inputs["query"]["query"]
    assert executor.request.inputs["query"]["external_context_sources"] == [
        "SPG_Company_KeyStats_10_orbixa_networks.xlsm"
    ]
    assert repository.created_turn is not None
    assert repository.created_turn["attachments"] == [
        {
            "id": "attachment-00000001",
            "name": "SPG_Company_KeyStats_10_orbixa_networks.xlsm",
            "content_type": attachment["content_type"],
            "size": 10_000,
        }
    ]


def test_combined_reader_receives_rag_answer_and_complete_attachment_context() -> None:
    tail_evidence = "Operating Income | FY2025 | 77"
    extracted_text = "[시트: Income Statement]\n" + ("Filler | 1\n" * 1_200) + tail_evidence
    attachment = {
        "attachment_id": "attachment-00000001",
        "file_name": "peer.xlsx",
        "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "file_size": 10_000,
        "extracted_text": extracted_text,
    }
    completion = RecordingCompletionClient()
    conversations = service(InMemoryChatRepository(attachment=attachment), completion)

    result = conversations._combined_attachment_rag_answer(
        "두 기업을 비교해줘",
        "Nexora Labs 매출은 120입니다.",
        attachment,
    )

    prompt = str(completion.input_items[0]["content"])
    assert result == "첨부 파일 분석 결과"
    assert "Nexora Labs 매출은 120입니다." in prompt
    assert extracted_text in prompt
    assert tail_evidence in prompt


def test_completed_summary_without_reader_output_keeps_chat_turn_processing() -> None:
    repository = InMemoryChatRepository()
    run = SimpleNamespace(status="completed", nodes={})
    conversations = service(
        repository,
        run_store=SimpleNamespace(load_summary=lambda _run_id: run),
    )

    result = conversations.sync_run("run-before-reader", "client-00000001")

    assert result["message"] is None
    assert repository.completed_turns == []
