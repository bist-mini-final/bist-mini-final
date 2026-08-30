"""HTTP adapter for reader cell-evidence verification."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.storage.pgvector_store import PgVectorStore
from backend.storage.spreadsheets.cell_evidence import locate_cell_artifact


def _matching_indexes(
    indexes: list[dict[str, Any]],
    company_name: str,
    workbook_hash: str,
    index_id: str,
    file_name: str,
) -> list[dict[str, Any]]:
    workbook_key = workbook_hash.strip().casefold()
    index_key = index_id.strip().casefold()
    file_key = file_name.strip().casefold()
    candidates = [
        item
        for item in indexes
        if (
            not workbook_key
            or str(item.get("workbook_hash") or "").strip().casefold() == workbook_key
        )
        and (
            not index_key
            or str(item.get("index_id") or "").strip().casefold() == index_key
        )
        and (
            not file_key
            or str(item.get("file_name") or "").strip().casefold() == file_key
        )
    ]
    if not company_name.strip():
        return candidates
    company_matches = [
        item
        for item in candidates
        if _company_alias_matches(item.get("company_name"), company_name)
    ]
    # Company names can be renamed after a run was persisted. Treat the name as a
    # preference, while workbook/index/file identifiers remain strict filters.
    return company_matches or candidates


_LEGAL_SUFFIXES = {
    "co",
    "company",
    "corp",
    "corporation",
    "inc",
    "incorporated",
    "limited",
    "llc",
    "ltd",
    "plc",
}


def _company_tokens(value: Any) -> list[str]:
    return [
        token
        for token in re.findall(r"[0-9a-z가-힣]+", str(value or "").casefold())
        if token not in _LEGAL_SUFFIXES
    ]


def _company_alias_matches(left: Any, right: Any) -> bool:
    left_tokens = _company_tokens(left)
    right_tokens = _company_tokens(right)
    if not left_tokens or not right_tokens:
        return False
    left_key = "".join(left_tokens)
    right_key = "".join(right_tokens)
    if left_key == right_key or left_key.startswith(right_key) or right_key.startswith(left_key):
        return True
    left_acronym = "".join(token[0] for token in left_tokens if token)
    right_acronym = "".join(token[0] for token in right_tokens if token)
    return left_key == right_acronym or right_key == left_acronym


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
        index_id: str = Query(default="", max_length=200),
        file_name: str = Query(default="", max_length=500),
        cell_value: str = Query(default="", max_length=500),
    ) -> dict[str, Any]:
        normalized_sheet = sheet_name.strip()
        normalized_coord = cell_coord.strip().upper()
        indexes = _matching_indexes(
            pgvector_store.list_indexes(),
            company_name,
            workbook_hash,
            index_id,
            file_name,
        )
        matches: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for index in indexes:
            collection_id = str(index.get("index_id") or "").strip()
            if not collection_id:
                continue
            cells = pgvector_store.fetch_cells_by_metadata(
                [normalized_coord],
                collection_name=collection_id,
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
        if company_name.strip():
            company_matches = [
                match
                for match in matches
                if _company_alias_matches(
                    match[1].get("company_name") or match[0].get("company_name"),
                    company_name,
                )
            ]
            if company_matches:
                matches = company_matches
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
        resolved_workbook_hash = str(
            cell.get("workbook_hash") or index.get("workbook_hash") or ""
        ).strip()
        resolved_file_name = str(
            cell.get("file_name") or index.get("file_name") or ""
        ).strip()
        image = locate_cell_artifact(
            processed_dir=processed_dir,
            artifact_dir=artifact_dir,
            file_name=resolved_file_name,
            workbook_hash=resolved_workbook_hash,
            sheet_name=normalized_sheet,
            cell_coord=normalized_coord,
        )
        return {
            "company_name": str(
                cell.get("company_name") or index.get("company_name") or company_name
            ).strip(),
            "index_id": str(index.get("index_id") or ""),
            "file_name": resolved_file_name,
            "workbook_hash": resolved_workbook_hash,
            "sheet_name": str(cell.get("sheet_name") or normalized_sheet),
            "cell_coord": str(cell.get("cell_coord") or normalized_coord),
            "cell_value": cell.get("cell_value"),
            "row_header": cell.get("row_header") or [],
            "column_header": cell.get("column_header") or [],
            "source_text": str(cell.get("source_text") or ""),
            "image": image,
        }

    return router
