"""HTTP route declarations for spreadsheet source files."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, File, Query, Request, UploadFile
from fastapi import Path as FastPath
from fastapi.responses import FileResponse

from modules.common.config import DEFAULT_EMBEDDING_MODEL

from .controller import DataSourceHttpController


def create_data_source_file_router(controller: DataSourceHttpController) -> APIRouter:
    """Declare source-file endpoints over the data-source controller."""
    router = APIRouter()

    @router.get(
        "/files",
        summary="업로드된 스프레드시트 원본 파일 목록 조회",
        description="업로드된 엑셀 파일 목록, 크기, 해시 및 인덱싱 상태를 조회합니다.",
    )
    def get_files() -> Dict[str, Any]:
        return controller.list_files()

    @router.get(
        "/files/{filename}/preview",
        summary="엑셀 시트 데이터 미리보기",
        description="지정된 엑셀 파일의 시트 목록 및 상위 N개 행을 조회합니다.",
    )
    def preview_file(
        filename: str = FastPath(..., description="조회할 파일명"),
        sheet_name: Optional[str] = Query(default=None, description="특정 시트명"),
        max_rows: int = Query(default=15, ge=1, le=50, description="미리볼 최대 행 수"),
    ) -> Dict[str, Any]:
        return controller.preview_file(filename, sheet_name, max_rows)

    @router.post(
        "/files/upload",
        summary="스프레드시트 파일 업로드 및 자동 인덱싱",
        description="엑셀 파일을 업로드하고 선택적으로 Kubernetes 인덱싱 큐에 등록합니다.",
    )
    async def upload_file(
        file: UploadFile = File(..., description="업로드할 엑셀 스프레드시트 파일"),
        auto_ingest: bool = Query(default=True, description="자동 인덱싱 여부"),
        model: str = Query(default=DEFAULT_EMBEDDING_MODEL, description="임베딩 모델"),
        batch_size: int = Query(default=2048, ge=1, le=2048, description="배치 크기"),
    ) -> Dict[str, Any]:
        return await controller.upload_file(
            file,
            auto_ingest=auto_ingest,
            model=model,
            batch_size=batch_size,
        )

    @router.get(
        "/files/{filename}/download",
        summary="스프레드시트 원본 파일 다운로드",
    )
    def download_file(
        filename: str = FastPath(..., description="다운로드할 파일명"),
    ) -> FileResponse:
        return controller.download_file(filename)

    @router.delete(
        "/files/{filename}",
        summary="업로드된 스프레드시트 파일 및 인덱스 삭제",
    )
    def remove_file(
        request: Request,
        filename: str = FastPath(..., description="삭제할 파일명"),
    ) -> Dict[str, Any]:
        return controller.delete_file(
            filename,
            getattr(request.state, "request_id", None),
        )

    return router


__all__ = ["create_data_source_file_router"]
