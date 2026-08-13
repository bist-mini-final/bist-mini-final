import re
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse


WORKBOOK_HASH_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


def _safe_sheet_name(value: str) -> str:
    return "".join(
        "_" if character in '\\/*?:\"<>| ' else character
        for character in value
    ).strip("_")


def create_spreadsheet_artifact_router(artifact_dir: Path) -> APIRouter:
    """Serve read-only spreadsheet render artifacts for result inspection."""

    router = APIRouter(tags=["Spreadsheet Artifacts"])

    @router.get("/spreadsheet-artifacts/{workbook_hash}/sheets/{sheet_name}")
    def get_sheet_artifact(
        workbook_hash: str,
        sheet_name: str,
        layer: Literal["rendered", "typed", "docling"] = Query(default="rendered"),
    ):
        if not WORKBOOK_HASH_PATTERN.fullmatch(workbook_hash):
            raise HTTPException(status_code=422, detail="올바른 workbook hash가 아닙니다")
        safe_sheet_name = _safe_sheet_name(sheet_name)
        if not safe_sheet_name:
            raise HTTPException(status_code=422, detail="올바른 시트 이름이 아닙니다")

        image_path = (
            artifact_dir
            / workbook_hash.lower()[:16]
            / layer
            / f"{safe_sheet_name}.png"
        )
        if not image_path.is_file():
            raise HTTPException(
                status_code=404,
                detail=f"시트 검사 이미지를 찾을 수 없습니다: {sheet_name}",
            )
        return FileResponse(
            image_path,
            media_type="image/png",
            headers={"Cache-Control": "private, max-age=31536000, immutable"},
        )

    return router
