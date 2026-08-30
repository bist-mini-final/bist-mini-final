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
from backend.providers.embeddings.ports import EmbeddingEncoder
from backend.storage.pgvector_store import PgVectorStore
from backend.storage.spreadsheets.ingestion import (
    delete_vector_index,
    get_vector_index_detail,
    list_processed_files,
    list_vector_indexes,
    preview_excel_sheet,
    search_vector_index,
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
        file_service: DataSourceFileService,
        pgvector_store: PgVectorStore,
        embedding_encoder: EmbeddingEncoder,
    ) -> None:
        self._processed_dir = processed_dir
        self._files = file_service
        self._vectors = pgvector_store
        self._embeddings = embedding_encoder

    def list_files(self) -> Dict[str, Any]:
        files = list_processed_files(self._processed_dir, self._vectors)
        return {"files": files, "total": len(files)}

    def preview_file(
        self,
        filename: str,
        sheet_name: Optional[str],
        max_rows: int,
    ) -> Dict[str, Any]:
        try:
            return preview_excel_sheet(
                filename,
                sheet_name=sheet_name,
                max_rows=max_rows,
                processed_dir=self._processed_dir,
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
        safe_filename = Path(filename).name
        target = self._processed_dir / safe_filename
        if not target.is_file():
            raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
        return FileResponse(
            target,
            filename=safe_filename,
            media_type="application/octet-stream",
        )

    def delete_file(self, filename: str, request_id: str | None) -> Dict[str, Any]:
        return self._files.delete(
            filename,
            actor_id="api-user",
            request_id=request_id,
        )

    def list_indexes(self) -> Dict[str, Any]:
        indexes = list_vector_indexes(self._vectors)
        return {"indexes": indexes, "total": len(indexes)}

    def get_index(self, index_id: str) -> Dict[str, Any]:
        detail = get_vector_index_detail(index_id, pgvector_store=self._vectors)
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
        if not self._vectors.update_index_company(index_id, company_name):
            raise HTTPException(status_code=404, detail=f"인덱스 {index_id}를 찾을 수 없습니다.")
        return {"status": "success", "index_id": index_id, "company_name": company_name}

    def delete_index(self, index_id: str) -> Dict[str, Any]:
        try:
            if not delete_vector_index(index_id, pgvector_store=self._vectors):
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
            results = search_vector_index(
                index_id=index_id,
                query_text=body.query,
                pgvector_store=self._vectors,
                embedding_encoder=self._embeddings,
                limit=body.limit,
            )
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
