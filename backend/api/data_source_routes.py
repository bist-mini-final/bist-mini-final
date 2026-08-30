"""Composition and file/index HTTP adapters for Data Sources."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi import Path as FastPath
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.core.settings import PROCESSED_DATA_DIR
from backend.domains.data_sources.application import (
    DataSourceFileService,
    UploadSourceFileCommand,
)
from backend.engine.workflows import (
    RunDispatcher,
    RunStore,
    WorkflowExecutor,
    WorkflowStore,
)
from backend.platform.data_sources import (
    IngestionSubmissionAdapter,
    SourceFileInspectorAdapter,
)
from backend.providers.embeddings.ports import EmbeddingEncoder
from backend.storage.data_sources import IngestionJobService
from backend.storage.db_manager import DatabaseManager
from backend.storage.pgvector_probe import PgVectorConnectionProbe
from backend.storage.pgvector_store import PgVectorStore
from backend.storage.spreadsheets.ingestion import (
    delete_vector_index,
    get_vector_index_detail,
    list_processed_files,
    list_vector_indexes,
    preview_excel_sheet,
    search_vector_index,
)
from modules.common.config import DEFAULT_EMBEDDING_MODEL

from .data_source_database_routes import create_database_router
from .data_source_ingestion_routes import create_ingestion_router

logger = logging.getLogger(__name__)


class SearchRequestDTO(BaseModel):
    """특정 벡터 인덱스 대상 즉시 유사도 검색 요청 DTO."""

    query: str = Field(min_length=1, description="검색할 질문 또는 텍스트")
    limit: int = Field(default=5, ge=1, le=50, description="반환할 최대 결과 수")


class UpdateIndexCompanyRequestDTO(BaseModel):
    """벡터 인덱스 바인딩 기업명 수정 요청 DTO."""

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
    """데이터 소스(파일, DB, pgvector 인덱스, 인덱싱 작업) 관리를 위한 FastAPI 라우터 생성."""
    router = APIRouter(prefix="/data-sources", tags=["데이터 소스 관리"])
    ingestion_jobs = IngestionJobService(
        workflow_store,
        run_store,
        workflow_executor,
        workflow_dispatcher,
    )
    file_service = DataSourceFileService(
        processed_dir=processed_dir,
        metadata=db_manager,
        vector_indexes=pgvector_store,
        ingestion=IngestionSubmissionAdapter(ingestion_jobs),
        inspector=SourceFileInspectorAdapter(),
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
        """업로드된 원본 스프레드시트 파일 목록 및 인덱싱 상태를 반환합니다."""
        files = list_processed_files(processed_dir, pgvector_store)
        return {"files": files, "total": len(files)}

    @router.get(
        "/files/{filename}/preview",
        summary="엑셀 시트 데이터 미리보기",
        description="지정된 엑셀 파일의 시트 목록 및 상위 N개 행의 원시 셀 데이터를 조회합니다.",
    )
    def preview_file(
        filename: str = FastPath(..., description="조회할 파일명 (예: 'sample.xlsx')"),
        sheet_name: Optional[str] = Query(
            default=None, description="특정 시트명 (기본값: 첫 번째 시트)"
        ),
        max_rows: int = Query(default=15, ge=1, le=50, description="미리볼 최대 행 수"),
    ) -> Dict[str, Any]:
        """업로드된 엑셀 파일의 원시 셀 데이터를 미리보기 형식으로 반환합니다."""
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
        model: str = Query(
            default=DEFAULT_EMBEDDING_MODEL, description="사용할 텍스트 임베딩 모델"
        ),
        batch_size: int = Query(default=2048, ge=1, le=2048, description="임베딩 배치 크기"),
    ) -> Dict[str, Any]:
        """새로운 엑셀 파일을 업로드하고 옵션에 따라 비동기 인덱싱 작업을 등록합니다."""
        if not file.filename:
            raise HTTPException(status_code=400, detail="유효한 파일명이 필요합니다.")

        async def chunks():
            while chunk := await file.read(1024 * 1024):
                yield chunk

        try:
            return await file_service.upload(
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

    @router.get(
        "/files/{filename}/download",
        summary="스프레드시트 원본 파일 다운로드",
        description="서버에 저장된 원본 엑셀 파일을 다운로드합니다.",
    )
    def download_file(
        filename: str = FastPath(..., description="다운로드할 파일명"),
    ) -> FileResponse:
        """업로드된 원본 스프레드시트 파일을 직접 다운로드합니다."""
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
        request: Request,
        filename: str = FastPath(..., description="삭제할 파일명"),
    ) -> Dict[str, Any]:
        """업로드된 원본 파일을 삭제하고 연결된 pgvector 벡터 인덱스를 제거합니다."""
        return file_service.delete(
            filename,
            actor_id="api-user",
            request_id=getattr(request.state, "request_id", None),
        )

    @router.get(
        "/indexes",
        summary="생성된 pgvector 벡터 인덱스 컬렉션 목록 조회",
        description="PostgreSQL에 생성된 모든 워크북 벡터 인덱스 컬렉션, 청크 수, 차원, 기업명을 조회합니다.",
    )
    def get_indexes() -> Dict[str, Any]:
        """생성된 모든 pgvector 벡터 인덱스 컬렉션 목록을 반환합니다."""
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
        """단일 벡터 인덱스 컬렉션의 메타데이터 및 청크 통계를 반환합니다."""
        detail = get_vector_index_detail(index_id, pgvector_store=pgvector_store)
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
        body: UpdateIndexCompanyRequestDTO = None,  # type: ignore[assignment]
    ) -> Dict[str, Any]:
        """특정 벡터 인덱스 컬렉션에 바인딩된 기업명을 업데이트합니다."""
        if body is None:
            raise HTTPException(status_code=422, detail="요청 본문이 필요합니다.")
        new_name = body.company_name.strip()
        if not new_name:
            raise HTTPException(status_code=422, detail="기업명은 비어있을 수 없습니다.")
        success = pgvector_store.update_index_company(index_id, new_name)
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
        """데이터베이스에서 특정 벡터 인덱스 컬렉션 및 임베딩을 완전히 삭제합니다."""
        try:
            success = delete_vector_index(index_id, pgvector_store=pgvector_store)
            if not success:
                raise HTTPException(status_code=404, detail="인덱스를 찾을 수 없습니다.")
            return {"status": "success", "message": f"{index_id} 인덱스가 삭제되었습니다."}
        except HTTPException:
            raise
        except Exception as error:
            raise HTTPException(
                status_code=500,
                detail=f"인덱스 삭제 중 오류 발생: {error}",
            ) from error

    @router.post(
        "/indexes/{index_id}/search",
        summary="단일 벡터 인덱스 대상 즉시 유사도 검색 테스트",
        description="질문 문자열을 즉시 임베딩하여 지정된 인덱스 내 상위 K개 셀 텍스트를 검색합니다.",
    )
    def search_index(
        index_id: str = FastPath(..., description="검색 대상 pgvector 컬렉션 ID"),
        body: SearchRequestDTO = None,  # type: ignore[assignment]
    ) -> Any:
        """지정된 인덱스 내에서 쿼리 임베딩을 통한 밀집 벡터 유사도 검색을 수행합니다."""
        if body is None:
            raise HTTPException(status_code=422, detail="요청 본문이 필요합니다.")
        try:
            results = search_vector_index(
                index_id=index_id,
                query_text=body.query,
                pgvector_store=pgvector_store,
                embedding_encoder=embedding_encoder,
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

    return router
