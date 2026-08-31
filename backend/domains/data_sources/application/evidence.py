"""Resolve reader citations to indexed cells and rendered sheet artifacts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

from backend.shared.domain import ApplicationConflict, ResourceNotFoundError


class CellEvidenceNotFoundError(ResourceNotFoundError):
    code = "CELL_EVIDENCE_NOT_FOUND"


class AmbiguousCellEvidenceError(ApplicationConflict):
    code = "AMBIGUOUS_CELL_EVIDENCE"


class CellEvidenceIndexPort(Protocol):
    def list_indexes(self) -> list[dict[str, Any]]: ...

    def fetch_cells_by_metadata(
        self,
        cell_identifiers: list[str],
        workbook_hash: str | None = None,
        company_name: str | None = None,
        collection_name: str | None = None,
        limit: int = 50,
        cell_references: list[dict[str, str | None]] | None = None,
    ) -> list[dict[str, Any]]: ...


class CellArtifactLocatorPort(Protocol):
    def locate(
        self,
        *,
        file_name: str,
        workbook_hash: str,
        sheet_name: str,
        cell_coord: str,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class CellEvidenceQuery:
    sheet_name: str
    cell_coord: str
    company_name: str = ""
    workbook_hash: str = ""
    index_id: str = ""
    file_name: str = ""
    cell_value: str = ""


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


def _matching_indexes(
    indexes: list[dict[str, Any]],
    query: CellEvidenceQuery,
) -> list[dict[str, Any]]:
    workbook_key = query.workbook_hash.strip().casefold()
    index_key = query.index_id.strip().casefold()
    file_key = query.file_name.strip().casefold()
    candidates = [
        item
        for item in indexes
        if (
            not workbook_key
            or str(item.get("workbook_hash") or "").strip().casefold() == workbook_key
        )
        and (not index_key or str(item.get("index_id") or "").strip().casefold() == index_key)
        and (not file_key or str(item.get("file_name") or "").strip().casefold() == file_key)
    ]
    if not query.company_name.strip():
        return candidates
    company_matches = [
        item
        for item in candidates
        if _company_alias_matches(item.get("company_name"), query.company_name)
    ]
    return company_matches or candidates


def _comparable_cell_value(value: Any) -> str:
    return str(value or "").strip().replace(",", "").casefold()


class CellEvidenceService:
    def __init__(
        self,
        indexes: CellEvidenceIndexPort,
        artifacts: CellArtifactLocatorPort,
    ) -> None:
        self._indexes = indexes
        self._artifacts = artifacts

    def resolve(self, query: CellEvidenceQuery) -> dict[str, Any]:
        normalized_sheet = query.sheet_name.strip()
        normalized_coord = query.cell_coord.strip().upper()
        indexes = _matching_indexes(self._indexes.list_indexes(), query)
        matches: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for index in indexes:
            collection_id = str(index.get("index_id") or "").strip()
            if not collection_id:
                continue
            cells = self._indexes.fetch_cells_by_metadata(
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
                if str(cell.get("sheet_name") or "").strip().casefold()
                == normalized_sheet.casefold()
                and str(cell.get("cell_coord") or "").strip().upper() == normalized_coord
            )
        if not matches:
            raise CellEvidenceNotFoundError(
                "인덱스에서 일치하는 셀 근거를 찾을 수 없습니다."
            )
        matches = self._prefer_exact_value_and_company(matches, query)
        if len({str(index.get("index_id") or "") for index, _ in matches}) > 1:
            raise AmbiguousCellEvidenceError(
                "같은 근거 좌표가 여러 원본 파일에 존재해 하나를 안전하게 선택할 수 없습니다."
            )
        index, cell = matches[0]
        workbook_hash = str(
            cell.get("workbook_hash") or index.get("workbook_hash") or ""
        ).strip()
        file_name = str(cell.get("file_name") or index.get("file_name") or "").strip()
        return {
            "company_name": str(
                cell.get("company_name") or index.get("company_name") or query.company_name
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
            "image": self._artifacts.locate(
                file_name=file_name,
                workbook_hash=workbook_hash,
                sheet_name=normalized_sheet,
                cell_coord=normalized_coord,
            ),
        }

    @staticmethod
    def _prefer_exact_value_and_company(
        matches: list[tuple[dict[str, Any], dict[str, Any]]],
        query: CellEvidenceQuery,
    ) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        requested_value = _comparable_cell_value(query.cell_value)
        if requested_value:
            value_matches = [
                match
                for match in matches
                if _comparable_cell_value(match[1].get("cell_value")) == requested_value
            ]
            if value_matches:
                matches = value_matches
        if query.company_name.strip():
            company_matches = [
                match
                for match in matches
                if _company_alias_matches(
                    match[1].get("company_name") or match[0].get("company_name"),
                    query.company_name,
                )
            ]
            if company_matches:
                matches = company_matches
        return matches


__all__ = [
    "AmbiguousCellEvidenceError",
    "CellArtifactLocatorPort",
    "CellEvidenceIndexPort",
    "CellEvidenceNotFoundError",
    "CellEvidenceQuery",
    "CellEvidenceService",
]
