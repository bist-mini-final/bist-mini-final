"""HTTP adapter for reader cell-evidence verification."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.storage.pgvector_store import PgVectorStore
from backend.storage.spreadsheets.cell_evidence import locate_cell_artifact


def _matching_indexes(
    indexes: list[dict[str, Any]],
    company_name: str,
    workbook_hash: str,
) -> list[dict[str, Any]]:
    company_key = company_name.strip().casefold()
    workbook_key = workbook_hash.strip().casefold()
    return [
        item
        for item in indexes
        if (
            not company_key
            or str(item.get("company_name") or "").strip().casefold() == company_key
        )
        and (
            not workbook_key
            or str(item.get("workbook_hash") or "").strip().casefold() == workbook_key
        )
    ]


def _comparable_cell_value(value: Any) -> str:
    return str(value or "").strip().replace(",", "").casefold()


def create_cell_evidence_router(
    *,
    pgvector_store: PgVectorStore,
    processed_dir: Path,
    artifact_dir: Path,
) -> APIRouter:
    """Create the exact-cell evidence lookup API used by reader citation badges."""
    router = APIRouter(prefix="/evidence", tags=["답변 근거 검증"])

    @router.get(
        "/cells/resolve",
        summary="Reader 답변의 셀 근거와 원본 시트 이미지 연결",
    )
    def resolve_cell_evidence(
        sheet_name: str = Query(min_length=1, max_length=200),
        cell_coord: str = Query(min_length=2, max_length=20),
        company_name: str = Query(default="", max_length=200),
        workbook_hash: str = Query(default="", max_length=64),
        cell_value: str = Query(default="", max_length=500),
    ) -> dict[str, Any]:
        normalized_sheet = sheet_name.strip()
        normalized_coord = cell_coord.strip().upper()
        indexes = _matching_indexes(
            pgvector_store.list_indexes(),
            company_name,
            workbook_hash,
        )
        matches: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for index in indexes:
            index_id = str(index.get("index_id") or "").strip()
            if not index_id:
                continue
            cells = pgvector_store.fetch_cells_by_metadata(
                [normalized_coord],
                collection_name=index_id,
                limit=2,
                cell_references=[
                    {
                        "cell_coord": normalized_coord,
                        "sheet_name": normalized_sheet,
                        "company_name": None,
                    }
                ],
            )
            matches.extend(
                (index, cell)
                for cell in cells
                if (
                    str(cell.get("sheet_name") or "").strip().casefold()
                    == normalized_sheet.casefold()
                    and str(cell.get("cell_coord") or "").strip().upper()
                    == normalized_coord
                )
            )

        if not matches:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "CELL_EVIDENCE_NOT_FOUND",
                    "message": "인덱스에서 일치하는 셀 근거를 찾을 수 없습니다.",
                    "retryable": False,
                },
            )
        requested_value = _comparable_cell_value(cell_value)
        if requested_value:
            value_matches = [
                match
                for match in matches
                if _comparable_cell_value(match[1].get("cell_value")) == requested_value
            ]
            if value_matches:
                matches = value_matches
        distinct_indexes = {str(index.get("index_id") or "") for index, _ in matches}
        if len(distinct_indexes) > 1:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "AMBIGUOUS_CELL_EVIDENCE",
                    "message": "같은 근거 좌표가 여러 원본 파일에 존재해 하나를 안전하게 선택할 수 없습니다.",
                    "retryable": False,
                },
            )

        index, cell = matches[0]
        workbook_hash = str(
            cell.get("workbook_hash") or index.get("workbook_hash") or ""
        ).strip()
        file_name = str(cell.get("file_name") or index.get("file_name") or "").strip()
        image = locate_cell_artifact(
            processed_dir=processed_dir,
            artifact_dir=artifact_dir,
            file_name=file_name,
            workbook_hash=workbook_hash,
            sheet_name=normalized_sheet,
            cell_coord=normalized_coord,
        )
        return {
            "company_name": str(
                cell.get("company_name") or index.get("company_name") or company_name
            ).strip(),
            "index_id": str(index.get("index_id") or ""),
            "file_name": file_name,
            "workbook_hash": workbook_hash,
            "sheet_name": str(cell.get("sheet_name") or normalized_sheet),
            "cell_coord": str(cell.get("cell_coord") or normalized_coord),
            "cell_value": cell.get("cell_value"),
            "row_header": cell.get("row_header") or [],
            "column_header": cell.get("column_header") or [],
            "source_text": str(cell.get("source_text") or ""),
            "image": image,
        }

    return router
