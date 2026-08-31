from __future__ import annotations

import logging
import re
from typing import Any, Protocol

from pydantic import ValidationError

from backend.shared.application.cell_evidence import CellEvidenceDTO, GroundedAnswerDTO

logger = logging.getLogger(__name__)

INSUFFICIENT_EVIDENCE_ANSWER = "확인 가능한 근거가 부족해 답변할 수 없습니다."


class ExecutionLogStorePort(Protocol):
    def get_node_execution_logs(self, run_id: str) -> list[dict[str, Any]]: ...


class EvidenceCellStorePort(Protocol):
    def fetch_cells_by_metadata(
        self,
        *,
        cell_identifiers: list[str],
        collection_name: str | None = None,
        workbook_hash: str | None = None,
        company_name: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]: ...


def _run_evidence_cells(run: Any) -> list[dict[str, str]]:
    """Return only source cells that the completed RAG run actually produced."""
    node = run.nodes.get("expand-context") if getattr(run, "nodes", None) else None
    output = node.output if node else None
    context = output.get("context_json", output) if isinstance(output, dict) else None
    cells = context.get("cells") if isinstance(context, dict) else None
    if not isinstance(cells, list):
        return []
    evidence: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for cell in cells:
        if not isinstance(cell, dict):
            continue
        sheet = str(cell.get("sheet_name") or "").strip()
        coord = str(cell.get("cell_coord") or "").strip().upper()
        index_id = str(cell.get("index_id") or "").strip()
        key = (index_id, sheet, coord)
        if not sheet or not re.fullmatch(r"[A-Z]{1,3}[1-9][0-9]{0,6}", coord) or key in seen:
            continue
        seen.add(key)
        evidence.append(
            {
                "index_id": index_id,
                "workbook_hash": str(cell.get("workbook_hash") or "").strip(),
                "company_name": str(cell.get("company_name") or "").strip(),
                "sheet_name": sheet,
                "cell_coord": coord,
            }
        )
    return evidence


def _recover_evidence_cells(
    run: Any,
    database: ExecutionLogStorePort | None,
    cell_store: EvidenceCellStorePort | None,
) -> list[dict[str, str]]:
    """Recover source cells when a Kubernetes worker externalized context output."""
    if database is None or cell_store is None:
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
        records = cell_store.fetch_cells_by_metadata(
            cell_identifiers=cell_ids,
            collection_name=document.get("index_id"),
            workbook_hash=document.get("workbook_hash"),
            company_name=document.get("company_name"),
            limit=30,
        )
    except Exception:
        logger.exception("Failed to recover chat evidence cells for run %s", getattr(run, "id", ""))
        return []
    return [
        {
            "index_id": str(record.get("index_id") or "").strip(),
            "workbook_hash": str(record.get("workbook_hash") or "").strip(),
            "company_name": str(record.get("company_name") or "").strip(),
            "sheet_name": str(record["sheet_name"]),
            "cell_coord": str(record["cell_coord"]).upper(),
        }
        for record in records
        if record.get("sheet_name")
        and re.fullmatch(r"[A-Z]{1,3}[1-9][0-9]{0,6}", str(record.get("cell_coord") or "").upper())
    ]


def _matches_run_evidence(selected: CellEvidenceDTO, actual: dict[str, str]) -> bool:
    if (
        selected.sheet_name.casefold() != actual["sheet_name"].casefold()
        or selected.cell_coord != actual["cell_coord"]
    ):
        return False
    selected_identity = {
        "index_id": selected.index_id or "",
        "workbook_hash": selected.workbook_hash,
        "company_name": selected.company_name or "",
    }
    return all(
        not actual[field]
        or actual[field].casefold() == selected_identity[field].casefold()
        for field in selected_identity
    )


def finalize_grounded_answer(
    answer_markdown: str | None,
    selected_evidence: list[dict[str, Any]] | None,
    run: Any,
    database: ExecutionLogStorePort | None = None,
    cell_store: EvidenceCellStorePort | None = None,
) -> GroundedAnswerDTO:
    """Validate Reader-selected evidence DTOs against cells produced by this run."""
    insufficient = GroundedAnswerDTO(
        answer_markdown=INSUFFICIENT_EVIDENCE_ANSWER,
        evidence=[],
    )
    if (
        not answer_markdown
        or answer_markdown.strip() == INSUFFICIENT_EVIDENCE_ANSWER
        or not selected_evidence
    ):
        return insufficient
    try:
        selected = [CellEvidenceDTO.model_validate(item) for item in selected_evidence]
    except ValidationError:
        logger.warning("Reader returned an invalid structured evidence payload")
        return insufficient
    evidence = _run_evidence_cells(run) or _recover_evidence_cells(run, database, cell_store)
    if not evidence:
        return insufficient
    if not all(any(_matches_run_evidence(item, actual) for actual in evidence) for item in selected):
        return insufficient
    return GroundedAnswerDTO(answer_markdown=answer_markdown, evidence=selected)


__all__ = [
    "EvidenceCellStorePort",
    "ExecutionLogStorePort",
    "INSUFFICIENT_EVIDENCE_ANSWER",
    "finalize_grounded_answer",
]
