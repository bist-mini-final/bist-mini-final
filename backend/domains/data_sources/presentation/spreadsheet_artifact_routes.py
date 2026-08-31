"""HTTP presentation for spreadsheet render artifacts."""

from typing import Literal

from fastapi import APIRouter, Query
from fastapi import Path as FastPath
from fastapi.responses import FileResponse

from backend.domains.data_sources.application.artifacts import SpreadsheetArtifactService


def create_spreadsheet_artifact_router(service: SpreadsheetArtifactService) -> APIRouter:
    router = APIRouter(tags=["스프레드시트 렌더 아티팩트"])

    @router.get(
        "/spreadsheet-artifacts/{workbook_hash}/sheets/{sheet_name}",
        summary="스프레드시트 시트 렌더링 아티팩트 이미지 조회",
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
        layer: Literal["rendered", "typed"] = Query(default="rendered"),
    ) -> FileResponse:
        image_path = service.resolve(workbook_hash, sheet_name, layer)
        return FileResponse(
            image_path,
            media_type="image/png",
            headers={"Cache-Control": "private, max-age=31536000, immutable"},
        )

    return router


__all__ = ["create_spreadsheet_artifact_router"]
