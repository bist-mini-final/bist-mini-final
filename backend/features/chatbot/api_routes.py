from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from backend.engine.workflows import (
    RunDispatcher,
    RunStore,
    WorkflowExecutionRequest,
    WorkflowExecutor,
    WorkflowStore,
)
from backend.features.bi.api_services import BiApiServices
from backend.providers.openai_responses import OpenAIResponsesClient, OpenAIResponsesError
from backend.storage.db_manager import DatabaseManager
from backend.storage.pgvector_store import PgVectorStore
from modules.common.config import DEFAULT_READER_MODEL

from .attachments import compact_evidence, save_upload
from .repository import ChatSessionRepository
from .suggestions import ChatSuggestionService


class CreateSessionRequest(BaseModel):
    client_id: str = Field(min_length=12, max_length=128)


class CreateMessageRequest(CreateSessionRequest):
    content: str = Field(min_length=1, max_length=1000)
    attachment_id: str | None = Field(default=None, min_length=12, max_length=64)


class RenameSessionRequest(CreateSessionRequest):
    title: str = Field(min_length=1, max_length=80)


def _reader_answer(run: Any) -> str | None:
    output = run.nodes.get("read").output if run.nodes.get("read") else None
    if not isinstance(output, dict):
        return None
    answer = output.get("answer_json", {}).get("answer") if isinstance(output.get("answer_json"), dict) else None
    return answer if isinstance(answer, str) and answer.strip() else None


_INSUFFICIENT_EVIDENCE_ANSWER = "확인 가능한 근거가 부족해 답변할 수 없습니다."
_CELL_CITATION_PATTERN = re.compile(
    r"\[Sheet:\s*(?P<sheet>[^\]|]+?)\s*\|\s*Cell:\s*(?P<coord>[A-Za-z]{1,3}[1-9][0-9]{0,6})\]"
)


def _run_evidence_cells(run: Any) -> list[tuple[str, str, str]]:
    """Return only source cells that the completed RAG run actually produced."""
    node = run.nodes.get("expand-context") if getattr(run, "nodes", None) else None
    output = node.output if node else None
    context = output.get("context_json", output) if isinstance(output, dict) else None
    cells = context.get("cells") if isinstance(context, dict) else None
    if not isinstance(cells, list):
        return []
    evidence: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for cell in cells:
        if not isinstance(cell, dict):
            continue
        sheet = str(cell.get("sheet_name") or "").strip()
        coord = str(cell.get("cell_coord") or "").strip().upper()
        source = str(cell.get("source_text") or "").strip()
        key = (sheet, coord)
        if not sheet or not re.fullmatch(r"[A-Z]{1,3}[1-9][0-9]{0,6}", coord) or key in seen:
            continue
        seen.add(key)
        evidence.append((sheet, coord, source))
    return evidence


def _recover_evidence_cells(run: Any, database: DatabaseManager | None) -> list[tuple[str, str, str]]:
    """Recover source cells when a Kubernetes worker externalized context output."""
    if database is None:
        return []
    try:
        logs = database.get_node_execution_logs(run.id)
        fusion = next((log for log in reversed(logs) if log["node_id"] == "fuse"), None)
        reader = next((log for log in reversed(logs) if log["node_id"] == "read"), None)
        fusion_output = fusion.get("output") if fusion else None
        reader_output = reader.get("output") if reader else None
        items = fusion_output.get("items") if isinstance(fusion_output, dict) else None
        answer_json = reader_output.get("answer_json") if isinstance(reader_output, dict) else None
        document = answer_json.get("document_context") if isinstance(answer_json, dict) else None
        if not isinstance(items, list) or not isinstance(document, dict):
            return []
        cell_ids = [str(item.get("cell_id") or "") for item in items[:30] if isinstance(item, dict)]
        records = PgVectorStore().fetch_cells_by_metadata(
            cell_identifiers=cell_ids,
            collection_name=document.get("index_id"),
            workbook_hash=document.get("workbook_hash"),
            company_name=document.get("company_name"),
            limit=30,
        )
    except Exception:
        return []
    return [
        (str(record["sheet_name"]), str(record["cell_coord"]).upper(), str(record.get("source_text") or ""))
        for record in records
        if record.get("sheet_name") and re.fullmatch(r"[A-Z]{1,3}[1-9][0-9]{0,6}", str(record.get("cell_coord") or "").upper())
    ]


def _finalize_grounded_answer(
    answer: str | None,
    run: Any,
    database: DatabaseManager | None = None,
) -> str:
    """Block unsupported RAG answers and attach source cells as chat citations."""
    if not answer or answer.strip() == _INSUFFICIENT_EVIDENCE_ANSWER:
        return _INSUFFICIENT_EVIDENCE_ANSWER
    evidence = _run_evidence_cells(run) or _recover_evidence_cells(run, database)
    if not evidence:
        return _INSUFFICIENT_EVIDENCE_ANSWER
    allowed = {(sheet.casefold(), coord) for sheet, coord, _ in evidence}
    citations = list(_CELL_CITATION_PATTERN.finditer(answer))
    if citations and not any(
        (match.group("sheet").strip().casefold(), match.group("coord").upper()) in allowed
        for match in citations
    ):
        return _INSUFFICIENT_EVIDENCE_ANSWER
    if not citations:
        sources = "\n".join(
            f"- [Sheet: {sheet} | Cell: {coord}] {source}"
            for sheet, coord, source in evidence[:6]
        )
        return f"{answer.rstrip()}\n\n**근거**\n{sources}"
    return answer


_RAG_TERMS = ("매출", "영업이익", "순이익", "자산", "부채", "자본", "현금흐름", "재무", "실적", "eps", "dps", "수치", "얼마", "몇", "분기", "연도")
_CHART_TERMS = ("그래프", "차트", "추이", "추세", "변화", "비교", "연도별")
_EXPLANATION_TERMS = (
    "뜻",
    "의미",
    "정의",
    "란",
    "무엇",
    "설명",
    "뭐야",
    "뭐예요",
    "뭔가요",
    "뭔지",
    "무엇인가요",
    "무엇이에요",
)
_DATA_REQUEST_TERMS = ("얼마", "몇", "20", "최신", "실적", "수치", "금액", "분기", "연도", "작년", "올해")
_RECENT_QUESTION_PATTERNS = (
    "방금 뭘 물어봤",
    "방금 무엇을 물어봤",
    "직전에 뭘 물어봤",
    "직전에 무엇을 물어봤",
    "내가 뭐 물어봤",
)
_COMPANY_ALIASES = {
    "bistelligence": ("비스텔리젼스", "비스텔리전스"),
}


def _company_aliases(name: str) -> tuple[str, ...]:
    """Return catalog, ticker, and supported Korean aliases for a company."""
    base_name = name.split("(", 1)[0].strip()
    tickers = re.findall(r"\b[A-Z]{2,8}\b", name)
    normalized_name = base_name.casefold()
    aliases = next(
        (values for key, values in _COMPANY_ALIASES.items() if normalized_name.startswith(key)),
        (),
    )
    return tuple(dict.fromkeys((name, base_name, *tickers, *aliases)))


def _is_recent_question_request(question: str) -> bool:
    normalized = re.sub(r"\s+", "", question)
    return any(re.sub(r"\s+", "", pattern) in normalized for pattern in _RECENT_QUESTION_PATTERNS)


def _company_identity_answer(company: str, question: str) -> str | None:
    """Answer short company-name confirmation and correction questions deterministically."""
    lowered = question.casefold()
    if not any(term in lowered for term in ("알아", "회사", "회사명", "서비스", "브랜드명", "이름")):
        return None
    return (
        f"네. 제공된 데이터 기준으로 **{company}**는 분석 대상 회사명입니다. "
        "서비스명이나 일반적인 솔루션명이 아닙니다."
    )


def _needs_rag(question: str, visualization: dict[str, str] | None) -> bool:
    """Route only requests for stored company data to the RAG workflow.

    A financial term on its own can be a request for a general definition.  In
    particular, Korean colloquialisms such as ``영업이익이 뭐야?`` must not
    retrieve every indexed company's result merely because they contain a
    financial metric name.
    """
    lowered = question.casefold()
    if visualization is not None:
        return True
    if any(term in lowered for term in _EXPLANATION_TERMS) and not any(
        marker in lowered for marker in _DATA_REQUEST_TERMS
    ):
        return False
    return any(term in lowered for term in _RAG_TERMS)


def _repair_inline_markdown_tables(answer: str) -> str:
    """Restore a GFM table when a model emits all of its rows on one line."""
    repaired_lines: list[str] = []
    for line in re.sub(r"\\+\|", "|", answer).splitlines():
        separator_start = line.find("|---")
        table_start = line.find("|")
        if separator_start < 0 or table_start < 0 or table_start >= separator_start:
            repaired_lines.append(line)
            continue

        header_cells = [cell.strip() for cell in line[table_start:separator_start].split("|") if cell.strip()]
        following_cells = [cell.strip() for cell in line[separator_start:].split("|") if cell.strip()]
        separator_cells = following_cells[:len(header_cells)]
        data_cells = following_cells[len(header_cells):]
        is_separator = all(re.fullmatch(r":?-{3,}:?", cell) for cell in separator_cells)
        row_count = len(data_cells) // len(header_cells)
        if len(header_cells) < 3 or not is_separator or not row_count:
            repaired_lines.append(line)
            continue

        rows = [
            data_cells[index:index + len(header_cells)]
            for index in range(0, row_count * len(header_cells), len(header_cells))
        ]
        table = [
            f"| {' | '.join(header_cells)} |",
            f"| {' | '.join(separator_cells)} |",
            *(f"| {' | '.join(row)} |" for row in rows),
        ]
        remainder = " | ".join(data_cells[row_count * len(header_cells):]).strip()
        rendered_table = "\n".join(table)
        suffix = f"\n{remainder}" if remainder else ""
        repaired_lines.append(f"{line[:table_start]}{rendered_table}{suffix}")
    return "\n".join(repaired_lines)


def _format_user_facing_answer(answer: str) -> str:
    """Keep missing-evidence disclosures while replacing raw source-system labels."""
    cleaned = _repair_inline_markdown_tables(answer)
    cleaned = re.sub(
        r"(?<![A-Za-z])NA(?![A-Za-z])\s*로?\s*근거가 부족(?:합니다|해요)?",
        "확인 가능한 근거가 부족해 요약에서 제외했습니다",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"(?<![A-Za-z])NA(?![A-Za-z])\s*로 표시되어 있어",
        "확인 가능한 값이 없어",
        cleaned,
        flags=re.IGNORECASE,
    )
    return re.sub(
        r"\s*[;\uff1b]\s*(?=(?:\*\*)?[^\n]*확인 가능한 근거가 부족)",
        "\n\n",
        cleaned,
    )


def _with_company_intro(answer: str, company: str | None, question: str) -> str:
    if not company:
        return answer
    short_name = company.split("(", 1)[0].strip()
    period = re.search(r"(20\d{2})년", question)
    lowered = question.casefold()
    if "현금흐름" in question or "cash flow" in lowered or "fcf" in lowered:
        topic = "현금흐름 추이"
    elif "총자산" in question and "총부채" in question:
        topic = "총자산과 총부채"
    elif "실적" in question:
        topic = f"{period.group(1)}년 최신 실적" if period else "최신 실적"
    elif "매출" in question:
        topic = "매출"
    else:
        topic = "재무 현황"
    intro = f"{company.strip()}의 {topic}는 다음과 같습니다."
    generic_intro = re.compile(
        rf"{re.escape(short_name)}(?:\s*\([^)]*\))?의\s*질문하신 항목은 다음과 같습니다\.",
        flags=re.IGNORECASE,
    )
    if generic_intro.search(answer[:240]):
        return generic_intro.sub(intro, answer, count=1)
    if short_name.casefold() in answer[:240].casefold():
        return answer
    return f"{intro}\n\n{answer}"


def _card_id(question: str) -> str:
    lowered = question.lower()
    if "매출" in lowered:
        return "revenue_growth"
    if "마진" in lowered or "이익률" in lowered:
        return "profitability"
    if "현금흐름" in lowered or "fcf" in lowered:
        return "cash_flow"
    if "자산" in lowered or "부채" in lowered or "자본" in lowered:
        return "financial_scale"
    return "stability"


def create_chat_router(*, db_manager: DatabaseManager, workflow_store: WorkflowStore, run_store: RunStore, workflow_executor: WorkflowExecutor, workflow_dispatcher: RunDispatcher, completion_client: OpenAIResponsesClient, bi_services: BiApiServices, suggestion_service: ChatSuggestionService) -> APIRouter:
    router = APIRouter(prefix="/chat", tags=["Chat"])
    repository = ChatSessionRepository(db_manager)

    def visualization_for(question: str) -> dict[str, str] | None:
        lowered = question.lower()
        if not any(term in lowered for term in _CHART_TERMS):
            return None
        for entry in bi_services.store.list_companies():
            if any(alias.casefold() in lowered for alias in _company_aliases(entry.company.display_name)):
                if bi_services.store.get_current(entry.company.company_id) is not None:
                    return {"company_id": str(entry.company.company_id), "card_id": _card_id(question)}
        return None

    def conversation_company(question: str, session_id: str) -> str | None:
        companies = repository.company_names()
        question_lower = question.casefold()
        for name in companies:
            if any(alias.casefold() in question_lower for alias in _company_aliases(name)):
                return name
        for message in repository.recent_user_messages(session_id):
            message_lower = message.casefold()
            for name in companies:
                if any(alias.casefold() in message_lower for alias in _company_aliases(name)):
                    return name
        return None

    def direct_answer(question: str, *, company: str | None, recent_messages: list[str]) -> str:
        context = "\n".join(f"- {message}" for message in recent_messages[:3])
        result = completion_client.create_response(
            model=DEFAULT_READER_MODEL,
            instructions=(
                "당신은 금융 서비스의 친절한 대화 도우미입니다. 제공된 사내 데이터는 직접 조회하지 않습니다. "
                "일상 대화와 금융 용어의 일반적 정의만 간결하게 답하고, 특정 기업의 최신 수치·실적은 데이터 조회가 필요하다고 안내하십시오. "
                "현재 질문이 금융 용어의 뜻·의미·정의(예: '영업이익이 뭐야?')라면 일반적인 정의만 답하고, "
                "최근 대화나 등록 기업의 이름, 기업별 수치·실적·표를 절대 덧붙이지 마십시오. "
                "대화 문맥의 대상 기업이 있으면 그 기업은 이 서비스의 등록 분석 대상 회사라고만 말하고, "
                "서비스명·제품명이라고 추측하지 마십시오. 최근 대화는 현재 질문의 대상 식별에만 사용하십시오."
            ),
            input_items=[{
                "role": "user",
                "content": (
                    f"최근 사용자 대화:\n{context or '- 없음'}\n\n"
                    f"대화 문맥의 대상 기업: {company or '없음'}\n\n"
                    f"현재 질문: {question}"
                ),
            }],
            max_output_tokens=400,
            max_retries=0,
        )
        return result.content

    def attachment_answer(question: str, attachment: dict[str, Any]) -> str:
        """Answer from the session-private extracted file content, not global RAG data."""
        source_name = str(attachment["file_name"])
        citation_name = source_name.replace("[", "(").replace("]", ")")
        evidence = compact_evidence(question, str(attachment["extracted_text"]))
        result = completion_client.create_response(
            model=DEFAULT_READER_MODEL,
            instructions=(
                "당신은 업로드된 파일을 근거로 답하는 금융 분석 도우미입니다. "
                "아래 첨부 파일 내용에 있는 정보만 사실로 사용하고, 파일에 없는 내용은 모른다고 말하십시오. "
                "핵심 근거가 되는 문장 또는 표의 값 뒤에는 반드시 "
                f"[{citation_name}: 첨부 근거] 형식의 출처를 붙이십시오. "
                "최대 8개 항목, 600자 이내로 간결하게 답하십시오. 마크다운 제목과 목록을 자연스럽게 사용하십시오."
            ),
            input_items=[{
                "role": "user",
                "content": f"질문: {question}\n\n[첨부 파일: {source_name}]\n{evidence}",
            }],
            max_output_tokens=1_600,
            max_retries=0,
        )
        return result.content

    def session_or_404(session_id: str, client_id: str) -> dict[str, Any]:
        session = repository.get_session(session_id, client_id)
        if session is None:
            raise HTTPException(status_code=404, detail="대화 세션을 찾을 수 없습니다")
        return session

    @router.get("/sessions")
    def list_sessions(client_id: str = Query(min_length=12, max_length=128)) -> dict[str, Any]:
        return {"sessions": repository.list_sessions(client_id)}

    @router.get("/suggestions")
    def list_suggestions() -> dict[str, list[str]]:
        return {"questions": suggestion_service.refresh_if_due()}

    @router.post("/suggestions/refresh")
    def refresh_suggestions() -> dict[str, list[str]]:
        return {"questions": suggestion_service.refresh_if_due(force=True)}

    @router.post("/sessions", status_code=201)
    def create_session(request: CreateSessionRequest) -> dict[str, Any]:
        return repository.create_session(request.client_id, "새 대화")

    @router.get("/sessions/{session_id}")
    def get_session(session_id: str, client_id: str = Query(min_length=12, max_length=128)) -> dict[str, Any]:
        return session_or_404(session_id, client_id)

    @router.patch("/sessions/{session_id}")
    def rename_session(session_id: str, request: RenameSessionRequest) -> dict[str, Any]:
        session_or_404(session_id, request.client_id)
        return repository.rename_session(session_id, request.client_id, request.title)

    @router.delete("/sessions/{session_id}")
    def delete_session(session_id: str, client_id: str = Query(min_length=12, max_length=128)) -> dict[str, str]:
        session_or_404(session_id, client_id)
        repository.delete_session(session_id, client_id)
        return {"deleted": session_id}

    @router.post("/sessions/{session_id}/attachments", status_code=201)
    async def upload_attachment(
        session_id: str,
        client_id: str = Form(min_length=12, max_length=128),
        file: UploadFile = File(...),
    ) -> dict[str, Any]:
        """Store a supported file privately under a chat session and extract its evidence text."""
        session_or_404(session_id, client_id)
        attachment_id, name, content_type, size, storage_path, extracted_text = await save_upload(file)
        return repository.create_attachment(
            session_id,
            attachment_id=attachment_id,
            file_name=name,
            content_type=content_type,
            file_size=size,
            storage_path=storage_path,
            extracted_text=extracted_text,
        )

    @router.post("/sessions/{session_id}/messages", status_code=202)
    def create_message(session_id: str, request: CreateMessageRequest) -> dict[str, Any]:
        session_or_404(session_id, request.client_id)
        try:
            attachment = repository.get_attachment(session_id, request.attachment_id) if request.attachment_id else None
            if request.attachment_id and attachment is None:
                raise HTTPException(status_code=404, detail="첨부 파일을 찾을 수 없습니다")
            attachment_meta = ([{
                "id": attachment["attachment_id"],
                "name": attachment["file_name"],
                "content_type": attachment["content_type"],
                "size": attachment["file_size"],
            }] if attachment else [])
            if attachment:
                return repository.create_direct_turn(
                    session_id,
                    request.content,
                    attachment_answer(request.content, attachment),
                    attachment_meta,
                )
            recent_messages = repository.recent_user_messages(session_id, limit=3)
            company = conversation_company(request.content, session_id)
            if _is_recent_question_request(request.content) and recent_messages:
                return repository.create_direct_turn(
                    session_id,
                    request.content,
                    f"방금 전에는 “{recent_messages[0]}”라고 물으셨습니다.",
                )
            identity_answer = _company_identity_answer(company, request.content) if company else None
            if identity_answer:
                return repository.create_direct_turn(session_id, request.content, identity_answer)
            visualization = visualization_for(request.content)
            if not _needs_rag(request.content, visualization):
                return repository.create_direct_turn(
                    session_id,
                    request.content,
                    direct_answer(request.content, company=company, recent_messages=recent_messages),
                )
            workflow = workflow_store.load("rag_query")
            query = request.content if company is None else (
                f"{request.content}\n\n[대화 문맥의 대상 기업: {company}]"
            )
            run = workflow_executor.create_run(workflow, WorkflowExecutionRequest(inputs={"query": {"query": query}}))
            workflow_dispatcher.submit(run.id)
            return repository.create_turn(session_id, request.content, run.id, visualization)
        except (RuntimeError, OpenAIResponsesError) as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @router.get("/runs/{run_id}")
    def sync_run(run_id: str, client_id: str = Query(min_length=12, max_length=128)) -> dict[str, Any]:
        if not repository.owns_run(run_id, client_id):
            raise HTTPException(status_code=404, detail="실행 Job을 찾을 수 없습니다")
        try:
            run = run_store.load_summary(run_id)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="실행 Job을 찾을 수 없습니다") from error
        message = None
        if run.status == "completed":
            session_id = repository.session_id_for_run(run_id)
            recent_questions = repository.recent_user_messages(session_id, limit=1) if session_id else []
            company = conversation_company("", session_id) if session_id else None
            answer = _format_user_facing_answer(
                _finalize_grounded_answer(_reader_answer(run), run, run_store.db_manager)
            )
            if answer != _INSUFFICIENT_EVIDENCE_ANSWER:
                answer = _with_company_intro(
                    answer,
                    company,
                    recent_questions[0] if recent_questions else "",
                )
            message = repository.complete_turn(
                run_id,
                "completed",
                answer,
                suppress_visualization=answer == _INSUFFICIENT_EVIDENCE_ANSWER,
            )
        elif run.status in ("failed", "paused"):
            failed = next((node.error for node in run.nodes.values() if node.status == "failed" and node.error), "질문 처리가 중지되었습니다.")
            message = repository.complete_turn(run_id, "failed", failed)
        return {"run": run, "message": message}

    return router
