"""API router for Data Sources (Files & Vector Indexes & pgvector DB)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field

from ..core.settings import (
    EMBEDDING_ARTIFACT_DIR,
    PGVECTOR_URL,
    PROCESSED_DATA_DIR,
    SPREADSHEET_ARTIFACT_DIR,
    VECTOR_INDEX_DIR,
)
from ..embeddings.factory import EmbeddingEncoder
from ..modules.base import ModuleExecutionError
from ..spreadsheets.ingestion import (
    delete_vector_index,
    get_vector_index_detail,
    ingest_excel_workbook,
    list_processed_files,
    list_vector_indexes,
    preview_excel_sheet,
    search_vector_index,
)
from ..storage.db_manager import DatabaseManager
from ..storage.embedding_artifacts import EmbeddingArtifactStore
from ..storage.pgvector_store import PgVectorStore
from ..storage.vector_index import VectorIndexStore


class IngestRequestDTO(BaseModel):
    file_name: str = Field(min_length=1, description="data/processed/ 내 대상 Excel 파일명")
    model: str = Field(
        default="text-embedding-3-large",
        description="임베딩 모델 (예: text-embedding-3-large, BAAI/bge-large-en-v1.5)",
    )
    variant_mode: Literal["header_only", "header_with_value", "both"] = Field(
        default="header_only",
        description="직렬화 형태 (header_only, header_with_value, both)",
    )
    structure_mode: Literal["auto", "luna_vlm", "exhaustive"] = Field(
        default="auto",
        description="구조화 모드 (auto: Luna VLM 감지 후 직렬화, luna_vlm: 강제 VLM, exhaustive: 전수 직렬화)",
    )
    sheet_names: Optional[List[str]] = Field(
        default=None,
        description="인덱싱할 시트 목록 (기본값: 모든 표시 시트)",
    )
    batch_size: int = Field(
        default=64,
        ge=1,
        le=512,
        description="임베딩 배치 크기",
    )


class SearchRequestDTO(BaseModel):
    query: str = Field(min_length=1, description="검색할 질문 또는 텍스트")
    limit: int = Field(default=5, ge=1, le=50, description="반환할 최대 결과 수")


class DbConnectRequestDTO(BaseModel):
    database_url: str = Field(min_length=1, description="PostgreSQL + pgvector 접속 URL")


class UpdateIndexCompanyRequestDTO(BaseModel):
    company_name: str = Field(min_length=1, max_length=200, description="수정할 기업명 / Entity Name")


def create_data_source_router(
    processed_dir: Path = PROCESSED_DATA_DIR,
    vector_index_dir: Path = VECTOR_INDEX_DIR,
    embedding_artifact_dir: Path = EMBEDDING_ARTIFACT_DIR,
    spreadsheet_artifact_dir: Path = SPREADSHEET_ARTIFACT_DIR,
    embedding_encoder: Optional[EmbeddingEncoder] = None,
    pgvector_store: Optional[PgVectorStore] = None,
) -> APIRouter:
    """
    Create the data-source API router and initialize its storage dependencies.
    
    Parameters:
        processed_dir (Path): Directory containing uploaded source files.
        vector_index_dir (Path): Directory containing local vector indexes.
        embedding_artifact_dir (Path): Directory containing embedding artifacts.
        spreadsheet_artifact_dir (Path): Directory containing spreadsheet artifacts.
        embedding_encoder (Optional[EmbeddingEncoder]): Encoder used for embedding operations.
        pgvector_store (Optional[PgVectorStore]): Existing pgvector store to use.
    
    Returns:
        APIRouter: Router exposing file, ingestion, vector-index, and database endpoints.
    """
    router = APIRouter(prefix="/data-sources", tags=["Data Sources"])

    vector_index_store = VectorIndexStore(vector_index_dir)
    embedding_artifact_store = EmbeddingArtifactStore(embedding_artifact_dir)
    pg_store = pgvector_store or PgVectorStore(PGVECTOR_URL)

    # 0. Database Status
    @router.get("/db-status")
    def get_db_status() -> Dict[str, Any]:
        """Get pgvector PostgreSQL connection status and statistics."""
        return pg_store.get_db_info()

    # 0-1. Test / Update DB Connection
    @router.post("/db-connect")
    def test_db_connect(req: DbConnectRequestDTO) -> Dict[str, Any]:
        """Test a given pgvector database URL."""
        test_store = PgVectorStore(req.database_url)
        return test_store.get_db_info()

    # 1. List files
    @router.get("/files")
    def get_files() -> Dict[str, Any]:
        """List all available raw files in data/processed/."""
        files = list_processed_files(processed_dir, vector_index_store, pg_store)
        return {"files": files, "total": len(files)}

    # 2. Preview Excel sheet
    @router.get("/files/{filename}/preview")
    def preview_file(
        filename: str,
        sheet_name: Optional[str] = Query(default=None),
        max_rows: int = Query(default=15, ge=1, le=50),
    ) -> Dict[str, Any]:
        """Preview content of an Excel sheet."""
        try:
            return preview_excel_sheet(
                filename,
                sheet_name=sheet_name,
                max_rows=max_rows,
                processed_dir=processed_dir,
            )
        except Exception as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    # 3. Upload file
    @router.post("/files/upload")
    async def upload_file(
        file: UploadFile = File(...),
        auto_ingest: bool = Query(default=True, description="업로드 즉시 Luna VLM 구조화 & 벡터 인덱싱 자동 실행"),
        model: str = Query(default="text-embedding-3-large", description="임베딩 모델"),
        batch_size: int = Query(default=64, description="임베딩 배치 크기"),
    ) -> Dict[str, Any]:
        """Upload a new raw file to data/processed/ and optionally trigger auto-ingest."""
        if not file.filename:
            raise HTTPException(status_code=400, detail="유효한 파일명이 필요합니다")

        safe_filename = Path(file.filename).name
        dest_path = processed_dir / safe_filename

        try:
            with dest_path.open("wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            file_bytes = dest_path.read_bytes()
            import hashlib
            file_hash = hashlib.sha256(file_bytes).hexdigest()
            db_mgr = DatabaseManager()
            if db_mgr.is_connected():
                db_mgr.save_source_file(
                    file_id=file_hash,
                    file_name=safe_filename,
                    file_hash=file_hash,
                    file_type=dest_path.suffix.lstrip(".").lower() or "bin",
                    file_size=len(file_bytes),
                    storage_path=f"data/source_files/{safe_filename}",
                )
        except Exception as error:
            raise HTTPException(status_code=500, detail=f"파일 저장 실패: {error}") from error
        finally:
            file.file.close()

        ingested_index = None
        ingest_error = None
        suffix = dest_path.suffix.lower()
        if auto_ingest and suffix in (".xlsx", ".xlsm"):
            try:
                ingested_index = ingest_excel_workbook(
                    file_name=safe_filename,
                    model=model,
                    batch_size=batch_size,
                    structure_mode="auto",
                    processed_dir=processed_dir,
                    spreadsheet_artifact_dir=spreadsheet_artifact_dir,
                    vector_index_store=vector_index_store,
                    pgvector_store=pg_store,
                    embedding_artifact_store=embedding_artifact_store,
                    embedding_encoder=embedding_encoder,
                )
            except Exception as err:
                import traceback
                traceback.print_exc()
                ingest_error = str(err)

        files = list_processed_files(processed_dir, vector_index_store, pg_store)
        uploaded = next((f for f in files if f["file_name"] == safe_filename), None)
        return {
            "status": "success",
            "file": uploaded,
            "auto_ingested": ingested_index is not None,
            "ingested_index": ingested_index,
            "error": ingest_error,
        }

    # 3-1. Download raw file from server disk storage
    @router.get("/files/{filename}/download")
    def download_file(filename: str) -> Response:
        """
        Download a processed file as an attachment.
        
        Parameters:
            filename (str): Name of the file to download.
        
        Returns:
            Response: File contents with an attachment disposition.
        
        Raises:
            HTTPException: If the requested file does not exist.
        """
        safe_filename = Path(filename).name
        target_path = processed_dir / safe_filename

        if not target_path.is_file():
            raise HTTPException(status_code=404, detail="다운로드할 파일을 찾을 수 없습니다")

        return Response(
            content=target_path.read_bytes(),
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{safe_filename}"'},
        )

    # 4. Delete file
    @router.delete("/files/{filename}")
    def delete_file(
        filename: str,
        cascade_indexes: bool = Query(default=True, description="연관된 벡터 인덱스도 함께 삭제(고아 벡터 방지)"),
    ) -> Dict[str, Any]:
        """Delete a raw file from data/processed/ with logical cascade to vector DB."""
        safe_filename = Path(filename).name
        target_path = processed_dir / safe_filename

        file_bytes = None
        workbook_hash = None
        if target_path.is_file():
            import hashlib
            file_bytes = target_path.read_bytes()
            workbook_hash = hashlib.sha256(file_bytes).hexdigest()
            target_path.unlink()

        db_mgr = DatabaseManager()
        if workbook_hash and db_mgr.is_connected():
            db_mgr.delete_source_file(workbook_hash)
        elif db_mgr.is_connected():
            db_mgr.delete_source_file(safe_filename)

        cascade_deleted = 0
        if cascade_indexes and workbook_hash and pg_store and pg_store.is_connected():
            cascade_deleted = pg_store.delete_by_workbook_hash(workbook_hash)

        return {
            "status": "success",
            "deleted_file": safe_filename,
            "cascade_indexes_deleted": cascade_deleted,
        }

    # 5. List vector indexes
    @router.get("/indexes")
    def get_indexes() -> Dict[str, Any]:
        """List all stored vector indexes."""
        indexes = list_vector_indexes(vector_index_dir, pg_store)
        return {"indexes": indexes, "total": len(indexes)}

    # 6. Get index detail
    @router.get("/indexes/{index_id}")
    def get_index(index_id: str) -> Dict[str, Any]:
        """Retrieve detailed information and sample items for a vector index."""
        try:
            return get_vector_index_detail(
                index_id,
                sample_items_count=20,
                vector_index_store=vector_index_store,
                pgvector_store=pg_store,
            )
        except Exception as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    # 6-1. Update index company name
    @router.patch("/indexes/{index_id}")
    @router.put("/indexes/{index_id}/company")
    def update_index_company(
        index_id: str,
        request: UpdateIndexCompanyRequestDTO,
    ) -> Dict[str, Any]:
        """Update company name in pgvector collection metadata and cascade to all chunks."""
        if not pg_store or not pg_store.is_connected():
            raise HTTPException(status_code=503, detail="pgvector 데이터베이스에 연결할 수 없습니다")
        try:
            return pg_store.update_index_company(index_id, request.company_name)
        except Exception as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    # 7. Delete vector index
    @router.delete("/indexes/{index_id}")
    def remove_index(index_id: str) -> Dict[str, Any]:
        """Delete a vector index from storage."""
        try:
            deleted = delete_vector_index(index_id, vector_index_store, pg_store)
            if not deleted:
                raise HTTPException(status_code=404, detail="삭제할 인덱스가 존재하지 않습니다")
            return {"status": "success", "deleted_index_id": index_id}
        except HTTPException:
            raise
        except Exception as error:
            raise HTTPException(status_code=500, detail=str(error)) from error

    # 8. Test similarity search
    @router.post("/indexes/{index_id}/search")
    def test_search(index_id: str, request: SearchRequestDTO) -> Dict[str, Any]:
        """Run similarity search test on a vector index."""
        try:
            hits = search_vector_index(
                index_id,
                query_text=request.query,
                limit=request.limit,
                vector_index_store=vector_index_store,
                pgvector_store=pg_store,
                embedding_encoder=embedding_encoder,
            )
            return {
                "index_id": index_id,
                "query": request.query,
                "results": hits,
                "total_results": len(hits),
            }
        except Exception as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    # 9. Ingest Excel workbook into Vector DB
    @router.post("/ingest")
    def ingest_workbook(request: IngestRequestDTO) -> Dict[str, Any]:
        """Execute end-to-end ingestion from Excel to Vector DB (pgvector & local store)."""
        try:
            result = ingest_excel_workbook(
                file_name=request.file_name,
                model=request.model,
                variant_mode=request.variant_mode,
                structure_mode=request.structure_mode,
                sheet_names=request.sheet_names,
                batch_size=request.batch_size,
                processed_dir=processed_dir,
                spreadsheet_artifact_dir=spreadsheet_artifact_dir,
                vector_index_store=vector_index_store,
                pgvector_store=pg_store,
                embedding_artifact_store=embedding_artifact_store,
                embedding_encoder=embedding_encoder,
            )
            return {"status": "success", "index": result}
        except ModuleExecutionError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=500, detail=f"인덱싱 처리 중 오류 발생: {error}") from error

    return router
