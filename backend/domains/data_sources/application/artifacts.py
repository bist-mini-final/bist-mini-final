"""Resolve immutable spreadsheet render artifacts through an injected store."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal, Protocol

from backend.shared.domain import ApplicationValidationError, ResourceNotFoundError

WORKBOOK_HASH_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


class SpreadsheetArtifactNotFoundError(ResourceNotFoundError):
    code = "SPREADSHEET_ARTIFACT_NOT_FOUND"


class SpreadsheetArtifactValidationError(ApplicationValidationError):
    code = "SPREADSHEET_ARTIFACT_INVALID"


class SpreadsheetArtifactStorePort(Protocol):
    def resolve(
        self,
        workbook_hash: str,
        sheet_name: str,
        layer: Literal["rendered", "typed"],
    ) -> Path | None: ...


class SpreadsheetArtifactService:
    def __init__(self, store: SpreadsheetArtifactStorePort) -> None:
        self._store = store

    def resolve(
        self,
        workbook_hash: str,
        sheet_name: str,
        layer: Literal["rendered", "typed"],
    ) -> Path:
        if not WORKBOOK_HASH_PATTERN.fullmatch(workbook_hash):
            raise SpreadsheetArtifactValidationError("올바른 workbook hash가 아닙니다.")
        image_path = self._store.resolve(workbook_hash, sheet_name, layer)
        if image_path is None:
            raise SpreadsheetArtifactNotFoundError(
                f"시트 검사 이미지를 찾을 수 없습니다: {sheet_name}"
            )
        return image_path


__all__ = [
    "SpreadsheetArtifactNotFoundError",
    "SpreadsheetArtifactService",
    "SpreadsheetArtifactStorePort",
    "SpreadsheetArtifactValidationError",
]
