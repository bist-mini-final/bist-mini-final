"""Local filesystem store for immutable spreadsheet render artifacts."""

from pathlib import Path
from typing import Literal

from backend.domains.data_sources.infrastructure.spreadsheets.cell_evidence import (
    safe_sheet_artifact_name,
)


class LocalSpreadsheetArtifactStore:
    def __init__(self, artifact_dir: Path) -> None:
        self._artifact_dir = artifact_dir

    def resolve(
        self,
        workbook_hash: str,
        sheet_name: str,
        layer: Literal["rendered", "typed"],
    ) -> Path | None:
        safe_sheet_name = safe_sheet_artifact_name(sheet_name)
        if not safe_sheet_name:
            return None
        image_path = (
            self._artifact_dir
            / workbook_hash.lower()[:16]
            / layer
            / f"{safe_sheet_name}.png"
        )
        return image_path if image_path.is_file() else None


__all__ = ["LocalSpreadsheetArtifactStore"]
