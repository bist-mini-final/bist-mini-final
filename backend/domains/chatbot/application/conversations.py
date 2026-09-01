"""Chat session use cases independent from FastAPI and concrete gateways."""

from __future__ import annotations

from typing import Any, Protocol

from backend.domains.chatbot.domain import (
    company_aliases,
    company_identity_answer,
    is_recent_question_request,
    needs_rag,
)
from backend.domains.workflow.domain.models import WorkflowExecutionRequest
from backend.shared.application.workbook_identity import workbook_file_identity
from backend.shared.domain import ResourceNotFoundError, RetryableInfrastructureError
from modules.common.config import DEFAULT_READER_MODEL

from .answer_formatting import (
    format_user_facing_answer,
    reader_answer,
    visualization_card_id,
    with_company_intro,
)
from .grounding import (
    INSUFFICIENT_EVIDENCE_ANSWER,
    finalize_grounded_answer,
)
from .ports import BiCompanyCatalogPort

_CHART_TERMS = ("그래프", "차트", "추이", "추세", "변화", "비교", "연도별")


class ChatNotFoundError(ResourceNotFoundError):
    code = "HTTP_404"


class ChatUnavailableError(RetryableInfrastructureError):
    code = "HTTP_503"


class CompletionResultPort(Protocol):
    @property
    def content(self) -> str: ...


class CompletionClientPort(Protocol):
    def create_response(
        self,
        *,
        model: str,
        input_items: list[dict[str, Any]],
        instructions: str | None = None,
        max_output_tokens: int | None = None,
        max_retries: int = 5,
    ) -> CompletionResultPort: ...


class ChatSessionRepositoryPort(Protocol):
    def create_session(self, client_id: str, title: str) -> dict[str, Any]: ...
    def list_sessions(self, client_id: str) -> list[dict[str, Any]]: ...
    def get_session(self, session_id: str, client_id: str) -> dict[str, Any] | None: ...
    def recent_user_messages(self, session_id: str, limit: int = 6) -> list[str]: ...
    def company_names(self) -> list[str]: ...
    def session_id_for_run(self, run_id: str) -> str | None: ...
    def rename_session(self, session_id: str, client_id: str, title: str) -> dict[str, Any]: ...
    def delete_session(self, session_id: str, client_id: str) -> None: ...
    def create_attachment(
        self,
        session_id: str,
        *,
        attachment_id: str,
        file_name: str,
        content_type: str | None,
        file_size: int,
        storage_path: str,
        extracted_text: str,
    ) -> dict[str, Any]: ...
    def get_attachment(self, session_id: str, attachment_id: str) -> dict[str, Any] | None: ...
    def get_attachment_for_run(self, run_id: str) -> dict[str, Any] | None: ...
    def create_turn(
        self,
        session_id: str,
        content: str,
        run_id: str,
        visualization: dict[str, str] | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]: ...
    def create_direct_turn(
        self,
        session_id: str,
        content: str,
        answer: str,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]: ...
    def complete_turn(
        self,
        run_id: str,
        status: str,
        content: str,
        *,
        evidence: list[dict[str, Any]] | None = None,
        suppress_visualization: bool = False,
    ) -> dict[str, Any] | None: ...
    def owns_run(self, run_id: str, client_id: str) -> bool: ...


class WorkflowStorePort(Protocol):
    def load(self, workflow_id: str) -> Any: ...


class WorkflowExecutorPort(Protocol):
    def create_run(self, workflow: Any, request: WorkflowExecutionRequest) -> Any: ...


class WorkflowDispatcherPort(Protocol):
    def submit(self, run_id: str, *, resume_failed: bool = False) -> bool: ...


class RunStorePort(Protocol):
    def load_summary(self, run_id: str) -> Any: ...

    def load_node(self, run_id: str, node_id: str) -> Any: ...


class ChatConversationService:
    """Coordinate session persistence, direct answers, and RAG-backed turns."""

    def __init__(
        self,
        *,
        repository: ChatSessionRepositoryPort,
        workflow_store: WorkflowStorePort,
        run_store: RunStorePort,
        workflow_executor: WorkflowExecutorPort,
        workflow_dispatcher: WorkflowDispatcherPort,
        completion_client: CompletionClientPort,
        bi_catalog: BiCompanyCatalogPort,
    ) -> None:
        self._repository = repository
        self._workflow_store = workflow_store
        self._run_store = run_store
        self._workflow_executor = workflow_executor
        self._workflow_dispatcher = workflow_dispatcher
        self._completion_client = completion_client
        self._bi_catalog = bi_catalog

    def list_sessions(self, client_id: str) -> dict[str, Any]:
        return {"sessions": self._repository.list_sessions(client_id)}

    def create_session(self, client_id: str) -> dict[str, Any]:
        return self._repository.create_session(client_id, "새 대화")

    def require_session(self, session_id: str, client_id: str) -> dict[str, Any]:
        session = self._repository.get_session(session_id, client_id)
        if session is None:
            raise ChatNotFoundError("대화 세션을 찾을 수 없습니다")
        return session

    def rename_session(self, session_id: str, client_id: str, title: str) -> dict[str, Any]:
        self.require_session(session_id, client_id)
        try:
            return self._repository.rename_session(session_id, client_id, title)
        except LookupError as error:
            raise ChatNotFoundError("대화 세션을 찾을 수 없습니다") from error

    def delete_session(self, session_id: str, client_id: str) -> dict[str, str]:
        self.require_session(session_id, client_id)
        self._repository.delete_session(session_id, client_id)
        return {"deleted": session_id}

    def create_attachment(
        self,
        session_id: str,
        *,
        attachment_id: str,
        file_name: str,
        content_type: str | None,
        file_size: int,
        storage_path: str,
        extracted_text: str,
    ) -> dict[str, Any]:
        return self._repository.create_attachment(
            session_id,
            attachment_id=attachment_id,
            file_name=file_name,
            content_type=content_type,
            file_size=file_size,
            storage_path=storage_path,
            extracted_text=extracted_text,
        )

    def create_message(
        self,
        session_id: str,
        client_id: str,
        content: str,
        attachment_id: str | None = None,
    ) -> dict[str, Any]:
        self.require_session(session_id, client_id)
        try:
            return self._create_message(session_id, content, attachment_id)
        except ChatNotFoundError:
            raise
        except RuntimeError as error:
            raise ChatUnavailableError(str(error)) from error

    def _create_message(
        self,
        session_id: str,
        content: str,
        attachment_id: str | None,
    ) -> dict[str, Any]:
        attachment = (
            self._repository.get_attachment(session_id, attachment_id) if attachment_id else None
        )
        if attachment_id and attachment is None:
            raise ChatNotFoundError("첨부 파일을 찾을 수 없습니다")

        recent_messages = self._repository.recent_user_messages(session_id, limit=3)
        company = self._conversation_company(content, session_id)
        visualization = self._visualization_for(content)
        if attachment and needs_rag(content, visualization):
            return self._create_rag_turn(
                session_id,
                content,
                company,
                visualization,
                attachment=attachment,
            )
        if attachment:
            return self._create_attachment_turn(session_id, content, attachment)
        if is_recent_question_request(content) and recent_messages:
            return self._repository.create_direct_turn(
                session_id,
                content,
                f"방금 전에는 “{recent_messages[0]}”라고 물으셨습니다.",
            )
        identity_answer = company_identity_answer(company, content) if company else None
        if identity_answer:
            return self._repository.create_direct_turn(session_id, content, identity_answer)
        if not needs_rag(content, visualization):
            answer = self._direct_answer(content, company=company, recent_messages=recent_messages)
            return self._repository.create_direct_turn(session_id, content, answer)
        return self._create_rag_turn(session_id, content, company, visualization)

    def _create_attachment_turn(
        self,
        session_id: str,
        content: str,
        attachment: dict[str, Any],
    ) -> dict[str, Any]:
        metadata = self._attachment_metadata(attachment)
        return self._repository.create_direct_turn(
            session_id,
            content,
            self._attachment_answer(content, attachment),
            metadata,
        )

    def _create_rag_turn(
        self,
        session_id: str,
        content: str,
        company: str | None,
        visualization: dict[str, str] | None,
        *,
        attachment: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        workflow = self._workflow_store.load("rag_query")
        query = content if company is None else f"{content}\n\n[대화 문맥의 대상 기업: {company}]"
        query_input: dict[str, Any] = {"query": query}
        if attachment is not None:
            query_input["external_context_sources"] = [str(attachment["file_name"])]
            identity = workbook_file_identity(str(attachment["file_name"]))
            if identity is not None:
                query_input["query"] += (
                    f"\n\n[첨부 파일명 기준 대상 기업: {identity.company_name}]"
                )
        run = self._workflow_executor.create_run(
            workflow,
            WorkflowExecutionRequest(inputs={"query": query_input}),
        )
        self._workflow_dispatcher.submit(run.id)
        return self._repository.create_turn(
            session_id,
            content,
            run.id,
            visualization,
            self._attachment_metadata(attachment) if attachment else None,
        )

    def sync_run(self, run_id: str, client_id: str) -> dict[str, Any]:
        if not self._repository.owns_run(run_id, client_id):
            raise ChatNotFoundError("실행 Job을 찾을 수 없습니다")
        try:
            run = self._run_store.load_summary(run_id)
        except FileNotFoundError as error:
            raise ChatNotFoundError("실행 Job을 찾을 수 없습니다") from error

        message = None
        if run.status == "completed":
            message = self._complete_successful_run(run_id, run)
        elif run.status in ("failed", "paused"):
            message = self._complete_failed_run(run_id, run)
        return {"run": run, "message": message}

    def _complete_successful_run(self, run_id: str, run: Any) -> dict[str, Any] | None:
        reader_result = reader_answer(run)
        if reader_result is None:
            # A summary can be observed while node rows are still being committed.
            # Keep the chat turn in processing state until the Reader contract exists.
            return None
        session_id = self._repository.session_id_for_run(run_id)
        recent_questions = (
            self._repository.recent_user_messages(session_id, limit=1) if session_id else []
        )
        company = self._conversation_company("", session_id) if session_id else None
        attachment = self._repository.get_attachment_for_run(run_id)
        grounded = finalize_grounded_answer(
            reader_result.answer_markdown,
            [item.model_dump(mode="json") for item in reader_result.evidence],
            run,
            self._run_store,
        )
        answer = format_user_facing_answer(grounded.answer_markdown)
        if attachment is not None:
            answer = format_user_facing_answer(
                self._combined_attachment_rag_answer(
                    recent_questions[0] if recent_questions else "",
                    answer,
                    attachment,
                )
            )
        elif answer != INSUFFICIENT_EVIDENCE_ANSWER:
            answer = with_company_intro(
                answer,
                company,
                recent_questions[0] if recent_questions else "",
            )
        return self._repository.complete_turn(
            run_id,
            "completed",
            answer,
            evidence=[item.model_dump(mode="json") for item in grounded.evidence],
            suppress_visualization=answer == INSUFFICIENT_EVIDENCE_ANSWER,
        )

    def _complete_failed_run(self, run_id: str, run: Any) -> dict[str, Any] | None:
        failure = next(
            (
                node.error
                for node in run.nodes.values()
                if node.status == "failed" and node.error
            ),
            "질문 처리가 중지되었습니다.",
        )
        return self._repository.complete_turn(run_id, "failed", failure)

    def _visualization_for(self, question: str) -> dict[str, str] | None:
        lowered = question.lower()
        if not any(term in lowered for term in _CHART_TERMS):
            return None
        for entry in self._bi_catalog.list_companies():
            if any(
                alias.casefold() in lowered
                for alias in company_aliases(entry.company.display_name)
            ) and self._bi_catalog.get_current(entry.company.company_id) is not None:
                return {
                    "company_id": str(entry.company.company_id),
                    "card_id": visualization_card_id(question),
                }
        return None

    def _conversation_company(self, question: str, session_id: str) -> str | None:
        companies = self._repository.company_names()
        messages = [question, *self._repository.recent_user_messages(session_id)]
        for message in messages:
            lowered = message.casefold()
            for name in companies:
                if any(alias.casefold() in lowered for alias in company_aliases(name)):
                    return name
        return None

    def _direct_answer(
        self,
        question: str,
        *,
        company: str | None,
        recent_messages: list[str],
    ) -> str:
        context = "\n".join(f"- {message}" for message in recent_messages[:3])
        result = self._completion_client.create_response(
            model=DEFAULT_READER_MODEL,
            instructions=(
                "당신은 금융 서비스의 친절한 대화 도우미입니다. 제공된 사내 데이터는 직접 조회하지 않습니다. "
                "일상 대화와 금융 용어의 일반적 정의만 간결하게 답하고, 특정 기업의 최신 수치·실적은 데이터 조회가 필요하다고 안내하십시오. "
                "현재 질문이 금융 용어의 뜻·의미·정의(예: '영업이익이 뭐야?')라면 일반적인 정의만 답하고, "
                "최근 대화나 등록 기업의 이름, 기업별 수치·실적·표를 절대 덧붙이지 마십시오. "
                "대화 문맥의 대상 기업이 있으면 그 기업은 이 서비스의 등록 분석 대상 회사라고만 말하고, "
                "서비스명·제품명이라고 추측하지 마십시오. 최근 대화는 현재 질문의 대상 식별에만 사용하십시오."
            ),
            input_items=[
                {
                    "role": "user",
                    "content": (
                        f"최근 사용자 대화:\n{context or '- 없음'}\n\n"
                        f"대화 문맥의 대상 기업: {company or '없음'}\n\n"
                        f"현재 질문: {question}"
                    ),
                }
            ],
            max_output_tokens=400,
            max_retries=0,
        )
        return result.content

    def _attachment_answer(self, question: str, attachment: dict[str, Any]) -> str:
        source_name = str(attachment["file_name"])
        citation_name = source_name.replace("[", "(").replace("]", ")")
        evidence = str(attachment["extracted_text"])
        identity = workbook_file_identity(source_name)
        identity_instruction = (
            f"첨부 파일명 기준 대상 기업은 '{identity.company_name}'입니다. "
            "워크북 내부에 남은 다른 회사명·티커는 템플릿 잔존값으로 취급하고 기업 식별에 "
            "사용하지 마십시오. 파일명에 티커가 없으므로 티커를 추측하지 마십시오. "
            if identity is not None
            else ""
        )
        result = self._completion_client.create_response(
            model=DEFAULT_READER_MODEL,
            instructions=(
                "당신은 업로드된 파일을 근거로 답하는 금융 분석 도우미입니다. "
                f"{identity_instruction}"
                "아래 첨부 파일 내용에 있는 정보만 사실로 사용하고, 파일에 없는 내용은 모른다고 말하십시오. "
                "핵심 근거가 되는 문장 또는 표의 값 뒤에는 반드시 "
                f"[{citation_name}: 첨부 근거] 형식의 출처를 붙이십시오. "
                "최대 8개 항목, 600자 이내로 간결하게 답하십시오. 마크다운 제목과 목록을 자연스럽게 사용하십시오."
            ),
            input_items=[
                {
                    "role": "user",
                    "content": (
                        f"질문: {question}\n\n"
                        f"[첨부 파일명 기준 기업: {identity.company_name if identity else '미확정'}]\n"
                        f"[첨부 파일: {source_name}]\n{evidence}"
                    ),
                }
            ],
            max_output_tokens=1_600,
            max_retries=0,
        )
        return result.content

    def _combined_attachment_rag_answer(
        self,
        question: str,
        rag_answer: str,
        attachment: dict[str, Any],
    ) -> str:
        source_name = str(attachment["file_name"])
        citation_name = source_name.replace("[", "(").replace("]", ")")
        evidence = str(attachment["extracted_text"])
        identity = workbook_file_identity(source_name)
        identity_instruction = (
            f"첨부 파일명 기준 대상 기업은 '{identity.company_name}'입니다. "
            "첨부 원문에 다른 회사명이나 티커가 남아 있어도 템플릿 잔존값이므로 기업 식별에 "
            "사용하거나 불일치 경고를 만들지 마십시오. 파일명에 없는 티커는 추측하지 마십시오. "
            if identity is not None
            else ""
        )
        result = self._completion_client.create_response(
            model=DEFAULT_READER_MODEL,
            instructions=(
                "당신은 서로 독립적인 두 검증 원천을 결합하는 금융 비교 분석가입니다. "
                f"{identity_instruction}"
                "'적재 기업 RAG 결과'는 서버가 셀 근거를 검증한 결과이므로 숫자와 기업명을 바꾸거나 "
                "추측하지 마십시오. '첨부 파일 원문'은 업로드 파일에서 평탄화한 전체 컨텍스트입니다. "
                "질문이 요구한 항목과 기간만 두 원천에서 찾아 같은 기준으로 비교하십시오. "
                "한쪽 값이 없으면 다른 항목으로 대체하지 말고 어느 원천에 무엇이 없는지 명시하십시오. "
                "첨부 파일의 사실·수치 뒤에는 반드시 "
                f"[{citation_name}: 첨부 근거]를 붙이십시오. "
                "적재 기업의 셀 출처는 서버가 별도 구조화 배지로 표시하므로 좌표나 가짜 출처를 본문에 "
                "만들지 마십시오. 1,200자 이내의 마크다운 표 또는 목록으로 답하십시오."
            ),
            input_items=[
                {
                    "role": "user",
                    "content": (
                        f"질문:\n{question}\n\n"
                        f"[적재 기업 RAG 결과]\n{rag_answer}\n\n"
                        f"[첨부 파일명 기준 기업: {identity.company_name if identity else '미확정'}]\n"
                        f"[첨부 파일: {source_name}]\n{evidence}"
                    ),
                }
            ],
            max_output_tokens=2_400,
            max_retries=0,
        )
        return result.content

    @staticmethod
    def _attachment_metadata(attachment: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "id": attachment["attachment_id"],
                "name": attachment["file_name"],
                "content_type": attachment["content_type"],
                "size": attachment["file_size"],
            }
        ]


__all__ = [
    "ChatConversationService",
    "ChatNotFoundError",
    "ChatSessionRepositoryPort",
    "ChatUnavailableError",
    "CompletionClientPort",
]
