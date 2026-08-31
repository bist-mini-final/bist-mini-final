from __future__ import annotations

import logging
import re
from typing import Any, Protocol

logger = logging.getLogger(__name__)

INSUFFICIENT_EVIDENCE_ANSWER = "확인 가능한 근거가 부족해 답변할 수 없습니다."
_CELL_CITATION_PATTERN = re.compile(
    r"\[Sheet:\s*(?P<sheet>[^\]|]+?)\s*\|\s*Cell:\s*(?P<coord>[A-Za-z]{1,3}[1-9][0-9]{0,6})\]"
)


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


def _recover_evidence_cells(
    run: Any,
    database: ExecutionLogStorePort | None,
    cell_store: EvidenceCellStorePort | None,
) -> list[tuple[str, str, str]]:
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
        (
            str(record["sheet_name"]),
            str(record["cell_coord"]).upper(),
            str(record.get("source_text") or ""),
        )
        for record in records
        if record.get("sheet_name")
        and re.fullmatch(r"[A-Z]{1,3}[1-9][0-9]{0,6}", str(record.get("cell_coord") or "").upper())
    ]


def finalize_grounded_answer(
    answer: str | None,
    run: Any,
    database: ExecutionLogStorePort | None = None,
    cell_store: EvidenceCellStorePort | None = None,
) -> str:
    """Block unsupported RAG answers and attach source cells as chat citations."""
    if not answer or answer.strip() == INSUFFICIENT_EVIDENCE_ANSWER:
        return INSUFFICIENT_EVIDENCE_ANSWER
    evidence = _run_evidence_cells(run) or _recover_evidence_cells(run, database, cell_store)
    if not evidence:
        return INSUFFICIENT_EVIDENCE_ANSWER
    allowed = {(sheet.casefold(), coord) for sheet, coord, _ in evidence}
    citations = list(_CELL_CITATION_PATTERN.finditer(answer))
    if citations and not any(
        (match.group("sheet").strip().casefold(), match.group("coord").upper()) in allowed
        for match in citations
    ):
        return INSUFFICIENT_EVIDENCE_ANSWER
    if not citations:
        sources = "\n".join(
            f"- [Sheet: {sheet} | Cell: {coord}] {source}" for sheet, coord, source in evidence[:6]
        )
        return f"{answer.rstrip()}\n\n**근거**\n{sources}"
    return answer


__all__ = [
    "EvidenceCellStorePort",
    "ExecutionLogStorePort",
    "INSUFFICIENT_EVIDENCE_ANSWER",
    "finalize_grounded_answer",
]
