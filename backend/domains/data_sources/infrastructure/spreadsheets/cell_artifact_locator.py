"""Spreadsheet cell artifact adapter."""

from pathlib import Path
from typing import Any

from .cell_evidence import locate_cell_artifact, locate_cell_artifacts


class LocalCellArtifactLocator:
    def __init__(self, processed_dir: Path, artifact_dir: Path) -> None:
        self._processed_dir = processed_dir
        self._artifact_dir = artifact_dir

    def locate(
        self,
        *,
        file_name: str,
        workbook_hash: str,
        sheet_name: str,
        cell_coord: str,
    ) -> dict[str, Any]:
        return locate_cell_artifact(
            processed_dir=self._processed_dir,
            artifact_dir=self._artifact_dir,
            file_name=file_name,
            workbook_hash=workbook_hash,
            sheet_name=sheet_name,
            cell_coord=cell_coord,
        )

    def locate_many(
        self,
        *,
        file_name: str,
        workbook_hash: str,
        sheet_name: str,
        cell_coords: list[str],
    ) -> dict[str, dict[str, Any]]:
        return locate_cell_artifacts(
            processed_dir=self._processed_dir,
            artifact_dir=self._artifact_dir,
            file_name=file_name,
            workbook_hash=workbook_hash,
            sheet_name=sheet_name,
            cell_coords=cell_coords,
        )


__all__ = ["LocalCellArtifactLocator"]
