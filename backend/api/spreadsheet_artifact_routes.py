"""HTTP API endpoints for serving visual spreadsheet render artifacts."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi import Path as FastPath
from fastapi.responses import FileResponse

WORKBOOK_HASH_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


def _safe_sheet_name(value: str) -> str:
    return "".join(
        "_" if character in '\\/*?:\"<>| ' else character
        for character in value
    ).strip("_")


def create_spreadsheet_artifact_router(artifact_dir: Path) -> APIRouter:
    """Luna VLM 및 구조 감지 엔진의 스프레드시트 렌더링 이미지 아티팩트 서빙 라우터 생성."""
    router = APIRouter(tags=["스프레드시트 렌더 아티팩트"])

    @router.get(
        "/spreadsheet-artifacts/{workbook_hash}/sheets/{sheet_name}",
        summary="스프레드시트 시트 렌더링 아티팩트 이미지 조회",
        description=(
            "Luna VLM 및 구조 감지 엔진에 의해 생성된 엑셀 시트의 "
            "고해상도 렌더링 이미지(rendered) 또는 셀 타입 마스킹 이미지(typed)를 반환합니다."
        ),
        response_class=FileResponse,
        responses={
            200: {"content": {"image/png": {}}, "description": "시트 렌더링 PNG 이미지"},
            404: {"description": "시트 검사 이미지를 찾을 수 없음"},
            422: {"description": "올바르지 않은 워크북 해시 또는 시트 이름"},
        },
    )
    def get_sheet_artifact(
        workbook_hash: str = FastPath(..., description="64자리 SHA256 워크북 콘텐츠 해시"),
        sheet_name: str = FastPath(..., description="엑셀 워크시트 이름"),
        layer: Literal["rendered", "typed"] = Query(
            default="rendered",
            description="이미지 레이어 종류 ('rendered': 원본 서식 렌더링, 'typed': 셀 타입 시각화)",
        ),
    ) -> FileResponse:
        """UI 시각 검사를 위한 스프레드시트 렌더링 PNG 아티팩트 이미지를 반환합니다."""
        if not WORKBOOK_HASH_PATTERN.fullmatch(workbook_hash):
            raise HTTPException(status_code=422, detail="올바른 workbook hash가 아닙니다.")
        safe_sheet_name = _safe_sheet_name(sheet_name)
        if not safe_sheet_name:
            raise HTTPException(status_code=422, detail="올바른 시트 이름이 아닙니다.")

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
