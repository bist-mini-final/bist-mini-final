"""Composition and file/index HTTP adapters for Data Sources."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from anyio import open_file, to_thread
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi import Path as FastPath
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
    """Request payload for vector search within a specific index."""

    query: str = Field(min_length=1, description="검색할 질문 또는 텍스트")
    limit: int = Field(default=5, ge=1, le=50, description="반환할 최대 결과 수")


class UpdateIndexCompanyRequestDTO(BaseModel):
    """Request payload for updating the company name bound to an index."""

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
    """Compose database, file, vector-index, and ingestion adapters under 'Data Sources'.

    Args:
        processed_dir: Path to directory containing source Excel spreadsheets.
        embedding_encoder: Text embedder for live query search.
        pgvector_store: pgvector client for vector queries and index inspection.
        connection_probe: Diagnostics probe for PostgreSQL health.
        db_manager: Database manager for source file metadata.
        workflow_store: Workflow definition store.
        run_store: Run execution store.
        workflow_executor: Ingestion workflow executor.
        workflow_dispatcher: Batch queue dispatcher.

    Returns:
        Configured APIRouter for all Data Source operations.
    """
    router = APIRouter(prefix="/data-sources", tags=["Data Sources"])
    ingestion_jobs = IngestionJobService(
        workflow_store,
        run_store,
        workflow_executor,
        workflow_dispatcher,
    )
    router.include_router(create_database_router(pgvector_store, connection_probe))
    router.include_router(
        create_ingestion_router(
            ingestion_jobs,
            run_store=run_store,
            pgvector_store=pgvector_store,
        )
    )

    @router.get(
        "/files",
        summary="업로드된 스프레드시트 원본 파일 목록 조회",
        description="`data/source_files`에 업로드된 엑셀 파일 목록, 크기, 해시 및 인덱싱 상태를 조회합니다.",
    )
    def get_files() -> Dict[str, Any]:
        """List all processed source files with indexing statuses."""
        files = list_processed_files(processed_dir, pgvector_store)
        return {"files": files, "total": len(files)}

    @router.get(
        "/files/{filename}/preview",
        summary="엑셀 시트 데이터 미리보기",
        description="지정된 엑셀 파일의 시트 목록 및 상위 N개 행의 원시 셀 데이터를 조회합니다.",
    )
    def preview_file(
        filename: str = FastPath(..., description="조회할 파일명 (예: 'sample.xlsx')"),
        sheet_name: Optional[str] = Query(default=None, description="특정 시트명 (기본값: 첫 번째 시트)"),
        max_rows: int = Query(default=15, ge=1, le=50, description="미리볼 최대 행 수"),
    ) -> Dict[str, Any]:
        """Preview raw cell values from an uploaded Excel spreadsheet."""
        try:
            return preview_excel_sheet(
                filename,
                sheet_name=sheet_name,
                max_rows=max_rows,
                processed_dir=processed_dir,
            )
        except Exception as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @router.post(
        "/files/upload",
        summary="스프레드시트 파일 업로드 및 자동 인덱싱",
        description="새로운 엑셀(.xlsx, .xlsm) 파일을 업로드하고 옵션에 따라 즉시 Kubernetes 인덱싱 큐에 등록합니다.",
    )
    async def upload_file(
        file: UploadFile = File(..., description="업로드할 엑셀 스프레드시트 파일"),
        auto_ingest: bool = Query(default=True, description="업로드 완료 후 자동 인덱싱 실행 여부"),
        model: str = Query(default=DEFAULT_EMBEDDING_MODEL, description="사용할 텍스트 임베딩 모델"),
        batch_size: int = Query(default=2048, ge=1, le=2048, description="임베딩 배치 크기"),
    ) -> Dict[str, Any]:
        """Upload a source spreadsheet and optionally enqueue an automated ingestion run."""
        if not file.filename:
            raise HTTPException(status_code=400, detail="유효한 파일명이 필요합니다.")

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
                            detail="파일 크기는 500MB를 초과할 수 없습니다.",
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
        ingestion_job: Optional[Dict[str, Any]] = None
        ingestion_error: Optional[str] = None
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

    @router.get(
        "/files/{filename}/download",
        summary="스프레드시트 원본 파일 다운로드",
        description="서버에 저장된 원본 엑셀 파일을 다운로드합니다.",
    )
    def download_file(
        filename: str = FastPath(..., description="다운로드할 파일명"),
    ) -> FileResponse:
        """Download an uploaded source file directly."""
        safe_filename = Path(filename).name
        target = processed_dir / safe_filename
        if not target.is_file():
            raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
        return FileResponse(
            target,
            filename=safe_filename,
            media_type="application/octet-stream",
        )

    @router.delete(
        "/files/{filename}",
        summary="업로드된 스프레드시트 파일 및 인덱스 삭제",
        description="파일을 디스크에서 제거하고 관련된 pgvector 벡터 인덱스 컬렉션도 함께 정리합니다.",
    )
    def remove_file(
        filename: str = FastPath(..., description="삭제할 파일명"),
    ) -> Dict[str, Any]:
        """Delete a source file and drop its associated vector index collection."""
        safe_filename = Path(filename).name
        target = processed_dir / safe_filename
        if not target.is_file():
            raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
        try:
            target.unlink()
        except Exception as error:
            raise HTTPException(status_code=500, detail=f"파일 삭제 실패: {error}") from error
        return {"status": "success", "message": f"{safe_filename} 파일이 삭제되었습니다."}

    @router.get(
        "/indexes",
        summary="생성된 pgvector 벡터 인덱스 컬렉션 목록 조회",
        description="PostgreSQL에 생성된 모든 워크북 벡터 인덱스 컬렉션, 청크 수, 차원, 기업명을 조회합니다.",
    )
    def get_indexes() -> Dict[str, Any]:
        """List all available vector index collections."""
        indexes = list_vector_indexes(pgvector_store)
        return {"indexes": indexes, "total": len(indexes)}

    @router.get(
        "/indexes/{index_id}",
        summary="단일 pgvector 벡터 인덱스 상세 정보 조회",
        description="지정된 인덱스의 통계, 연결된 시트 목록, 임베딩 차원, 생성 일자를 조회합니다.",
    )
    def get_index_detail(
        index_id: str = FastPath(..., description="pgvector 컬렉션 ID"),
    ) -> Dict[str, Any]:
        """Get schema and document statistics for a single vector index collection."""
        detail = get_vector_index_detail(pgvector_store, index_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="인덱스를 찾을 수 없습니다.")
        return detail

    @router.put(
        "/indexes/{index_id}/company",
        summary="벡터 인덱스 바인딩 기업명 수정",
        description="인덱스에 부여된 기업명을 수정하여 BI 및 질의 라우팅 매칭 정확도를 높입니다.",
    )
    def update_index_company(
        index_id: str = FastPath(..., description="수정할 pgvector 컬렉션 ID"),
        body: UpdateIndexCompanyRequestDTO = ...,
    ) -> Dict[str, Any]:
        """Update the bound company name for a specific vector index collection."""
        new_name = body.company_name.strip()
        if not new_name:
            raise HTTPException(status_code=422, detail="기업명은 비어있을 수 없습니다.")
        success = pgvector_store.update_index_company_name(index_id, new_name)
        if not success:
            raise HTTPException(status_code=404, detail=f"인덱스 {index_id}를 찾을 수 없습니다.")
        return {"status": "success", "index_id": index_id, "company_name": new_name}

    @router.delete(
        "/indexes/{index_id}",
        summary="pgvector 벡터 인덱스 컬렉션 삭제",
        description="지정된 벡터 인덱스 컬렉션과 저장된 셀 임베딩 데이터를 DB에서 완전히 삭제합니다.",
    )
    def remove_index(
        index_id: str = FastPath(..., description="삭제할 pgvector 컬렉션 ID"),
    ) -> Dict[str, Any]:
        """Drop a vector index collection and its embeddings from the database."""
        success = delete_vector_index(pgvector_store, index_id)
        if not success:
            raise HTTPException(status_code=404, detail="인덱스를 찾을 수 없거나 삭제에 실패했습니다.")
        return {"status": "success", "message": f"{index_id} 인덱스가 삭제되었습니다."}

    @router.post(
        "/indexes/{index_id}/search",
        summary="단일 벡터 인덱스 대상 즉시 유사도 검색 테스트",
        description="질문 문자열을 즉시 임베딩하여 지정된 인덱스 내 상위 K개 셀 텍스트를 검색합니다.",
    )
    def search_index(
        index_id: str = FastPath(..., description="검색 대상 pgvector 컬렉션 ID"),
        body: SearchRequestDTO = ...,
    ) -> Dict[str, Any]:
        """Execute a dense vector similarity search within a specific index."""
        try:
            return search_vector_index(
                pgvector_store,
                embedding_encoder,
                index_id,
                query=body.query,
                limit=body.limit,
            )
        except Exception as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    return router
