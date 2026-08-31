"""Presentation controller for spreadsheet files and vector indexes."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.domains.data_sources.application import (
    DataSourceFileService,
    UploadSourceFileCommand,
)
from backend.domains.data_sources.application.ports import (
    DataSourceCatalogPort,
    SourceFileStoragePort,
)


class SearchRequestDTO(BaseModel):
    """Immediate similarity-search request."""

    query: str = Field(min_length=1, description="검색할 질문 또는 텍스트")
    limit: int = Field(default=5, ge=1, le=50, description="반환할 최대 결과 수")


class UpdateIndexCompanyRequestDTO(BaseModel):
    """Company binding update request."""

    company_name: str = Field(
        min_length=1,
        max_length=200,
        description="수정할 기업명 / Entity Name",
    )


class DataSourceHttpController:
    """Translate file and vector-index operations into HTTP responses."""

    def __init__(
        self,
        *,
        processed_dir: Path,
        file_storage: SourceFileStoragePort,
        file_service: DataSourceFileService,
        catalog: DataSourceCatalogPort,
    ) -> None:
        self._processed_dir = processed_dir
        self._file_storage = file_storage
        self._files = file_service
        self._catalog = catalog

    def list_files(self) -> Dict[str, Any]:
        files = self._catalog.list_files(self._processed_dir)
        return {"files": files, "total": len(files)}

    def preview_file(
        self,
        filename: str,
        sheet_name: Optional[str],
        max_rows: int,
    ) -> Dict[str, Any]:
        try:
            return self._catalog.preview_file(
                self._processed_dir,
                filename,
                sheet_name=sheet_name,
                max_rows=max_rows,
            )
        except Exception as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    async def upload_file(
        self,
        file: UploadFile,
        *,
        auto_ingest: bool,
        model: str,
        batch_size: int,
    ) -> Dict[str, Any]:
        if not file.filename:
            raise HTTPException(status_code=400, detail="유효한 파일명이 필요합니다.")

        async def chunks():
            while chunk := await file.read(1024 * 1024):
                yield chunk

        try:
            return await self._files.upload(
                UploadSourceFileCommand(
                    file_name=file.filename,
                    auto_ingest=auto_ingest,
                    model=model,
                    batch_size=batch_size,
                ),
                chunks(),
            )
        finally:
            await file.close()

    def download_file(self, filename: str) -> FileResponse:
        target = self._file_storage.resolve_existing(filename)
        if target is None:
            raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
        return FileResponse(
            target,
            filename=target.name,
            media_type="application/octet-stream",
        )

    def delete_file(self, filename: str, request_id: str | None) -> Dict[str, Any]:
        return self._files.delete(
            filename,
            actor_id="api-user",
            request_id=request_id,
        )

    def list_indexes(self) -> Dict[str, Any]:
        indexes = self._catalog.list_indexes()
        return {"indexes": indexes, "total": len(indexes)}

    def get_index(self, index_id: str) -> Dict[str, Any]:
        detail = self._catalog.get_index(index_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="인덱스를 찾을 수 없습니다.")
        return detail

    def update_index_company(
        self,
        index_id: str,
        body: UpdateIndexCompanyRequestDTO | None,
    ) -> Dict[str, Any]:
        if body is None:
            raise HTTPException(status_code=422, detail="요청 본문이 필요합니다.")
        company_name = body.company_name.strip()
        if not company_name:
            raise HTTPException(status_code=422, detail="기업명은 비어있을 수 없습니다.")
        if not self._catalog.update_index_company(index_id, company_name):
            raise HTTPException(status_code=404, detail=f"인덱스 {index_id}를 찾을 수 없습니다.")
        return {"status": "success", "index_id": index_id, "company_name": company_name}

    def delete_index(self, index_id: str) -> Dict[str, Any]:
        try:
            if not self._catalog.delete_index(index_id):
                raise HTTPException(status_code=404, detail="인덱스를 찾을 수 없습니다.")
            return {"status": "success", "message": f"{index_id} 인덱스가 삭제되었습니다."}
        except HTTPException:
            raise
        except Exception as error:
            raise HTTPException(
                status_code=500,
                detail=f"인덱스 삭제 중 오류 발생: {error}",
            ) from error

    def search_index(
        self,
        index_id: str,
        body: SearchRequestDTO | None,
    ) -> Dict[str, Any]:
        if body is None:
            raise HTTPException(status_code=422, detail="요청 본문이 필요합니다.")
        try:
            results = self._catalog.search_index(index_id, body.query, body.limit)
            return {
                "index_id": index_id,
                "query": body.query,
                "results": results,
                "total_results": len(results),
            }
        except Exception as error:
            raise HTTPException(status_code=400, detail=str(error)) from error


__all__ = [
    "DataSourceHttpController",
    "SearchRequestDTO",
    "UpdateIndexCompanyRequestDTO",
]
