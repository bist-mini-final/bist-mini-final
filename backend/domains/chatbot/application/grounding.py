from __future__ import annotations

import logging
import re
from typing import Any, Protocol

from pydantic import ValidationError

from backend.shared.application.cell_evidence import CellEvidenceDTO, GroundedAnswerDTO

logger = logging.getLogger(__name__)

INSUFFICIENT_EVIDENCE_ANSWER = "확인 가능한 근거가 부족해 답변할 수 없습니다."


class RunNodeStorePort(Protocol):
    def load_node(self, run_id: str, node_id: str) -> Any: ...


def _context_evidence_cells(output: Any) -> list[dict[str, str]]:
    """Normalize the concrete cells emitted by the context-expansion boundary."""
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


def _run_evidence_cells(run: Any) -> list[dict[str, str]]:
    """Return only source cells included in a non-compacted run summary."""
    node = run.nodes.get("expand-context") if getattr(run, "nodes", None) else None
    return _context_evidence_cells(node.output if node else None)


def _persisted_context_evidence_cells(
    run: Any,
    run_nodes: RunNodeStorePort | None,
) -> list[dict[str, str]]:
    """Hydrate the exact context-expansion artifact omitted from run summaries."""
    if run_nodes is None:
        return []
    try:
        expanded = run_nodes.load_node(run.id, "expand-context")
        return _context_evidence_cells(expanded.output)
    except Exception:
        logger.exception(
            "Failed to hydrate expanded chat context for run %s",
            getattr(run, "id", ""),
        )
        return []


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
        not selected_identity[field]
        or actual[field].casefold() == selected_identity[field].casefold()
        for field in selected_identity
    )


def finalize_grounded_answer(
    answer_markdown: str | None,
    selected_evidence: list[dict[str, Any]] | None,
    run: Any,
    run_nodes: RunNodeStorePort | None = None,
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
    evidence = _run_evidence_cells(run) or _persisted_context_evidence_cells(run, run_nodes)
    if not evidence:
        return insufficient
    if not all(any(_matches_run_evidence(item, actual) for actual in evidence) for item in selected):
        return insufficient
    return GroundedAnswerDTO(answer_markdown=answer_markdown, evidence=selected)


__all__ = [
    "INSUFFICIENT_EVIDENCE_ANSWER",
    "RunNodeStorePort",
    "finalize_grounded_answer",
]
