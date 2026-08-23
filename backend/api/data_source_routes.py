"""Composition and file/index HTTP adapters for Data Sources."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from anyio import open_file, to_thread
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.core.settings import PROCESSED_DATA_DIR
from backend.engine.workflows import (
    RunDispatcher,
    RunStore,
    WorkflowExecutor,
    WorkflowStore,
)
from backend.providers.embeddings.ports import EmbeddingEncoder
from backend.storage.data_sources import IngestionJobService
from backend.storage.data_sources import IngestionRequest as IngestRequestDTO
from backend.storage.db_manager import DatabaseManager
from backend.storage.pgvector_probe import PgVectorConnectionProbe
from backend.storage.pgvector_store import PgVectorStore
from backend.storage.spreadsheets.ingestion import (
    delete_vector_index,
    get_processed_file_info,
    get_vector_index_detail,
    list_processed_files,
    list_vector_indexes,
    preview_excel_sheet,
    search_vector_index,
)
from modules.common.config import DEFAULT_EMBEDDING_MODEL

from .data_source_database_routes import create_database_router
from .data_source_ingestion_routes import create_ingestion_router

MAX_UPLOAD_SIZE_BYTES = 500 * 1024 * 1024
_WORKBOOK_SUFFIXES = frozenset({".xlsx", ".xlsm"})
_HASHED_FILE_SUFFIXES = frozenset({".xlsx", ".xlsm", ".json"})
logger = logging.getLogger(__name__)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class SearchRequestDTO(BaseModel):
    query: str = Field(min_length=1, description="검색할 질문 또는 텍스트")
    limit: int = Field(default=5, ge=1, le=50, description="반환할 최대 결과 수")


class UpdateIndexCompanyRequestDTO(BaseModel):
    company_name: str = Field(
        min_length=1,
        max_length=200,
        description="수정할 기업명 / Entity Name",
    )


def create_data_source_router(
    *,
    processed_dir: Path = PROCESSED_DATA_DIR,
    embedding_encoder: EmbeddingEncoder,
    pgvector_store: PgVectorStore,
    connection_probe: PgVectorConnectionProbe,
    db_manager: DatabaseManager,
    workflow_store: WorkflowStore,
    run_store: RunStore,
    workflow_executor: WorkflowExecutor,
    workflow_dispatcher: RunDispatcher,
) -> APIRouter:
    """Compose database, file, vector-index, and ingestion adapters."""
    router = APIRouter(prefix="/data-sources", tags=["Data Sources"])
    ingestion_jobs = IngestionJobService(
        workflow_store,
        run_store,
        workflow_executor,
        workflow_dispatcher,
    )
    router.include_router(create_database_router(pgvector_store, connection_probe))

    @router.get("/files")
    def get_files() -> dict[str, Any]:
        files = list_processed_files(processed_dir, pgvector_store)
        return {"files": files, "total": len(files)}

    @router.get("/files/{filename}/preview")
    def preview_file(
        filename: str,
        sheet_name: str | None = Query(default=None),
        max_rows: int = Query(default=15, ge=1, le=50),
    ) -> dict[str, Any]:
        try:
            return preview_excel_sheet(
                filename,
                sheet_name=sheet_name,
                max_rows=max_rows,
                processed_dir=processed_dir,
            )
        except Exception as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @router.post("/files/upload")
    async def upload_file(
        file: UploadFile = File(...),
        auto_ingest: bool = Query(default=True),
        model: str = Query(default=DEFAULT_EMBEDDING_MODEL),
        batch_size: int = Query(default=2048, ge=1, le=2048),
    ) -> dict[str, Any]:
        if not file.filename:
            raise HTTPException(status_code=400, detail="유효한 파일명이 필요합니다")

        safe_filename = Path(file.filename).name
        destination = processed_dir / safe_filename
        temporary = processed_dir / f".{safe_filename}.{uuid4().hex}.uploading"
        try:
            processed_dir.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            size_bytes = 0
            async with await open_file(temporary, "wb") as buffer:
                while chunk := await file.read(1024 * 1024):
                    size_bytes += len(chunk)
                    if size_bytes > MAX_UPLOAD_SIZE_BYTES:
                        raise HTTPException(
                            status_code=413,
                            detail="파일 크기는 500MB를 초과할 수 없습니다",
                        )
                    digest.update(chunk)
                    await buffer.write(chunk)
            await to_thread.run_sync(temporary.replace, destination)
            file_hash = digest.hexdigest()
        except HTTPException:
            if temporary.exists():
                temporary.unlink()
            raise
        except Exception as error:
            if temporary.exists():
                temporary.unlink()
            raise HTTPException(
                status_code=500,
                detail=f"파일 저장 실패: {error}",
            ) from error
        finally:
            await file.close()

        if await to_thread.run_sync(db_manager.is_connected):
            try:
                await to_thread.run_sync(
                    lambda: db_manager.save_source_file(
                        file_id=file_hash,
                        file_name=safe_filename,
                        file_hash=file_hash,
                        file_type=destination.suffix.lstrip(".").lower() or "bin",
                        file_size=destination.stat().st_size,
                        storage_path=str(destination.resolve()),
                    )
                )
            except Exception as error:
                logger.warning("업로드 파일 DB 메타데이터 저장 실패: %s", error)

        suffix = destination.suffix.casefold()
        ingestion_job: dict[str, Any] | None = None
        ingestion_error: str | None = None
        if auto_ingest and suffix in _WORKBOOK_SUFFIXES:
            try:
                request = IngestRequestDTO(
                    file_name=safe_filename,
                    model=model,
                    batch_size=batch_size,
                )
                run = await to_thread.run_sync(
                    ingestion_jobs.create_and_submit,
                    request,
                )
                ingestion_job = ingestion_jobs.payload(run)
            except Exception as error:
                logger.exception("업로드 후 자동 인덱싱 제출 실패: %s", safe_filename)
                ingestion_error = str(error)

        uploaded = await to_thread.run_sync(
            lambda: get_processed_file_info(
                destination,
                workbook_hash=(file_hash if suffix in _HASHED_FILE_SUFFIXES else None),
            )
        )
        return {
            "status": "success",
            "file": uploaded,
            "ingestion_job": ingestion_job,
            "error": ingestion_error,
        }

    @router.get("/files/{filename}/download")
    def download_file(filename: str) -> FileResponse:
        safe_filename = Path(filename).name
        target = processed_dir / safe_filename
        if not target.is_file():
            raise HTTPException(status_code=404, detail="다운로드할 파일을 찾을 수 없습니다")
        return FileResponse(
            path=target,
            media_type="application/octet-stream",
            filename=safe_filename,
        )

    @router.delete("/files/{filename}")
    def delete_file(
        filename: str,
        cascade_indexes: bool = Query(default=True),
    ) -> dict[str, Any]:
        safe_filename = Path(filename).name
        target = processed_dir / safe_filename
        workbook_hash = _sha256_file(target) if target.is_file() else None
        if target.is_file():
            target.unlink()

        if db_manager.is_connected():
            db_manager.delete_source_file(workbook_hash or safe_filename)
        deleted_indexes = 0
        if cascade_indexes and workbook_hash and pgvector_store.is_connected():
            deleted_indexes = pgvector_store.delete_by_workbook_hash(workbook_hash)
        return {
            "status": "success",
            "deleted_file": safe_filename,
            "cascade_indexes_deleted": deleted_indexes,
        }

    @router.get("/indexes")
    def get_indexes() -> dict[str, Any]:
        indexes = list_vector_indexes(pgvector_store)
        return {"indexes": indexes, "total": len(indexes)}

    @router.get("/indexes/{index_id}")
    def get_index(index_id: str) -> dict[str, Any]:
        try:
            return get_vector_index_detail(
                index_id,
                sample_items_count=20,
                pgvector_store=pgvector_store,
            )
        except Exception as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @router.patch("/indexes/{index_id}")
    @router.put("/indexes/{index_id}/company")
    def update_index_company(
        index_id: str,
        request: UpdateIndexCompanyRequestDTO,
    ) -> dict[str, Any]:
        if not pgvector_store.is_connected():
            raise HTTPException(
                status_code=503,
                detail="pgvector 데이터베이스에 연결할 수 없습니다",
            )
        try:
            return pgvector_store.update_index_company(
                index_id,
                request.company_name,
            )
        except Exception as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @router.delete("/indexes/{index_id}")
    def remove_index(index_id: str) -> dict[str, Any]:
        try:
            if not delete_vector_index(index_id, pgvector_store):
                raise HTTPException(
                    status_code=404,
                    detail="삭제할 인덱스가 존재하지 않습니다",
                )
            return {"status": "success", "deleted_index_id": index_id}
        except HTTPException:
            raise
        except Exception as error:
            raise HTTPException(status_code=500, detail=str(error)) from error

    @router.post("/indexes/{index_id}/search")
    def test_search(index_id: str, request: SearchRequestDTO) -> dict[str, Any]:
        try:
            hits = search_vector_index(
                index_id,
                query_text=request.query,
                limit=request.limit,
                pgvector_store=pgvector_store,
                embedding_encoder=embedding_encoder,
            )
        except Exception as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {
            "index_id": index_id,
            "query": request.query,
            "results": hits,
            "total_results": len(hits),
        }

    router.include_router(
        create_ingestion_router(ingestion_jobs, run_store, pgvector_store)
    )
    return router


__all__ = ["create_data_source_router"]
