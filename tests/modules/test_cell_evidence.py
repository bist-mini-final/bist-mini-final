from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook
from PIL import Image

from backend.domains.data_sources.application import CellEvidenceService
from backend.domains.data_sources.infrastructure.spreadsheets import LocalCellArtifactLocator
from backend.domains.data_sources.infrastructure.spreadsheets.cell_evidence import (
    locate_cell_artifact,
)
from backend.domains.data_sources.presentation import create_cell_evidence_router


class FakePgVectorStore:
    def __init__(self, *, file_name: str, workbook_hash: str) -> None:
        self.file_name = file_name
        self.workbook_hash = workbook_hash

    def list_indexes(self) -> list[dict[str, Any]]:
        return [
            {
                "index_id": "idx_amesoft",
                "company_name": "AmeSoft",
                "file_name": self.file_name,
                "workbook_hash": self.workbook_hash,
            }
        ]

    def fetch_cells_by_metadata(self, *_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        return [
            {
                "company_name": "AmeSoft",
                "sheet_name": "Income_Statement",
                "cell_coord": "E16",
                "cell_value": "4836",
                "row_header": ["Revenue"],
                "column_header": ["Fiscal Year Ended", "2014-12-31"],
                "source_text": "Company: AmeSoft | Sheet: Income_Statement | Cell Value: 4836",
            }
        ]


def _write_workbook(processed_dir: Path) -> tuple[str, str]:
    file_name = "amesoft.xlsx"
    workbook_path = processed_dir / file_name
    workbook = Workbook()
    worksheet = workbook.active
    assert worksheet is not None
    worksheet.title = "Income_Statement"
    worksheet["E16"] = 4836
    workbook.save(workbook_path)
    workbook.close()
    workbook_hash = hashlib.sha256(workbook_path.read_bytes()).hexdigest()
    return file_name, workbook_hash


def test_locate_cell_artifact_returns_scaled_cell_bounds(tmp_path: Path) -> None:
    processed_dir = tmp_path / "source_files"
    artifact_dir = tmp_path / "artifacts"
    processed_dir.mkdir()
    file_name, workbook_hash = _write_workbook(processed_dir)
    rendered_dir = artifact_dir / workbook_hash[:16] / "rendered"
    rendered_dir.mkdir(parents=True)
    Image.new("RGB", (800, 600), "white").save(rendered_dir / "Income_Statement.png")

    result = locate_cell_artifact(
        processed_dir=processed_dir,
        artifact_dir=artifact_dir,
        file_name=file_name,
        workbook_hash=workbook_hash,
        sheet_name="Income_Statement",
        cell_coord="E16",
    )

    assert result["rendered_available"] is True
    assert result["image_width"] == 800
    assert result["image_height"] == 600
    x1, y1, x2, y2 = result["cell_bbox_px"]
    assert 0 <= x1 < x2 <= 800
    assert 0 <= y1 < y2 <= 600


def test_cell_evidence_route_scopes_lookup_by_company(tmp_path: Path) -> None:
    processed_dir = tmp_path / "source_files"
    artifact_dir = tmp_path / "artifacts"
    processed_dir.mkdir()
    file_name, workbook_hash = _write_workbook(processed_dir)
    rendered_dir = artifact_dir / workbook_hash[:16] / "rendered"
    rendered_dir.mkdir(parents=True)
    Image.new("RGB", (800, 600), "white").save(rendered_dir / "Income_Statement.png")

    app = FastAPI()
    app.include_router(
        create_cell_evidence_router(
            CellEvidenceService(
                FakePgVectorStore(
                    file_name=file_name,
                    workbook_hash=workbook_hash,
                ),  # type: ignore[arg-type]
                LocalCellArtifactLocator(processed_dir, artifact_dir),
            )
        )
    )
    response = TestClient(app).get(
        "/evidence/cells/resolve",
        params={
            "company_name": "AmeSoft",
            "sheet_name": "Income_Statement",
            "cell_coord": "E16",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["company_name"] == "AmeSoft"
    assert body["cell_value"] == "4836"
    assert body["image"]["rendered_available"] is True
    assert body["image"]["cell_bbox_px"] is not None


def test_cell_evidence_route_accepts_persisted_full_company_alias(tmp_path: Path) -> None:
    processed_dir = tmp_path / "source_files"
    artifact_dir = tmp_path / "artifacts"
    processed_dir.mkdir()
    file_name, workbook_hash = _write_workbook(processed_dir)
    rendered_dir = artifact_dir / workbook_hash[:16] / "rendered"
    rendered_dir.mkdir(parents=True)
    Image.new("RGB", (800, 600), "white").save(rendered_dir / "Income_Statement.png")

    app = FastAPI()
    app.include_router(
        create_cell_evidence_router(
            CellEvidenceService(
                FakePgVectorStore(
                    file_name=file_name,
                    workbook_hash=workbook_hash,
                ),  # type: ignore[arg-type]
                LocalCellArtifactLocator(processed_dir, artifact_dir),
            )
        )
    )
    response = TestClient(app).get(
        "/evidence/cells/resolve",
        params={
            "company_name": "AmeSoft Holdings Inc. (AMES)",
            "sheet_name": "Income_Statement",
            "cell_coord": "E16",
            "cell_value": "4,836",
        },
    )

    assert response.status_code == 200
    assert response.json()["company_name"] == "AmeSoft"
