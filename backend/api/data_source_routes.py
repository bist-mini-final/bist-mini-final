"""API router for Data Sources (Files & Vector Indexes & pgvector DB)."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..data_sources import IngestionJobService, IngestionRequest as IngestRequestDTO
from ..core.settings import (
    EMBEDDING_ARTIFACT_DIR,
    PGVECTOR_URL,
    PREFECT_DEPLOYMENT_NAME,
    PROCESSED_DATA_DIR,
    RUN_DIR,
    SPREADSHEET_ARTIFACT_DIR,
    VECTOR_INDEX_DIR,
    WORKFLOW_DIR,
    CACHE_DIR,
)
from ..embeddings.factory import EmbeddingEncoder
from ..spreadsheets.ingestion import (
    delete_vector_index,
    get_processed_file_info,
    get_vector_index_detail,
    list_processed_files,
    list_vector_indexes,
    preview_excel_sheet,
    search_vector_index,
)
from ..storage.db_manager import DatabaseManager
from ..storage.embedding_artifacts import EmbeddingArtifactStore
from ..storage.pgvector_store import PgVectorStore
from ..storage.vector_index import VectorIndexStore
from ..storage.answer_cache import AnswerCacheRepository
from ..runtime.registry import ModuleRegistry
from ..workflows import (
    DagExecutionError,
    RunDispatcher,
    ResultCache,
    RunStore,
    WorkflowExecutor,
    WorkflowStore,
)


MAX_UPLOAD_SIZE_BYTES = 500 * 1024 * 1024
logger = logging.getLogger(__name__)

_ALLOWED_DB_HOSTS = frozenset(
    {
        "localhost",
        "127.0.0.1",
        "::1",
        "postgres",
        "pgvector",
        "bist-pgvector",
    }
)


def _is_allowed_database_host(host: Optional[str], port: Optional[int]) -> bool:
    if not host:
        return False
    normalized = host.strip("[]").lower()
    if normalized in _ALLOWED_DB_HOSTS:
        # Only allow port 5432 or the configured PGVECTOR_URL port
        allowed_ports = {5432}
        try:
            configured_port = urlparse(PGVECTOR_URL).port
            if configured_port:
                allowed_ports.add(configured_port)
        except Exception:
            pass
        if port is not None and port not in allowed_ports:
            return False
        return True
    try:
        configured_host = urlparse(PGVECTOR_URL).hostname
        if configured_host and normalized == configured_host.strip("[]").lower():
            # Also validate port for configured host
            allowed_ports = {5432}
            configured_port = urlparse(PGVECTOR_URL).port
            if configured_port:
                allowed_ports.add(configured_port)
            if port is not None and port not in allowed_ports:
                return False
            return True
    except Exception as err:
        logger.warning("Failed to parse configured PGVECTOR_URL: %s", err)
    return False


def _sha256_file(path: Path) -> str:
    """Compute the SHA-256 digest of a file.
    
    Parameters:
        path (Path): Path to the file to hash.
    
    Returns:
        str: The file's SHA-256 digest in hexadecimal form.
    """
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    workflow_dir: Path = WORKFLOW_DIR,
    run_dir: Path = RUN_DIR,
    cache_dir: Path = CACHE_DIR,
    embedding_encoder: Optional[EmbeddingEncoder] = None,
    pgvector_store: Optional[PgVectorStore] = None,
    module_registry: Optional[ModuleRegistry] = None,
    workflow_store: Optional[WorkflowStore] = None,
    run_store: Optional[RunStore] = None,
    workflow_executor: Optional[WorkflowExecutor] = None,
    workflow_dispatcher: Optional[RunDispatcher] = None,
) -> APIRouter:
    """
    Create the data-source API router and configure file, vector-index, database, and ingestion workflow services.
    
    Parameters:
    	processed_dir (Path): Directory containing uploaded source files.
    	vector_index_dir (Path): Directory for vector-index artifacts.
    	embedding_artifact_dir (Path): Directory for embedding artifacts.
    	spreadsheet_artifact_dir (Path): Directory for spreadsheet artifacts.
    	workflow_dir (Path): Directory containing workflow definitions.
    	run_dir (Path): Directory for persisted workflow runs.
    	cache_dir (Path): Directory for cached workflow results.
    	embedding_encoder (Optional[EmbeddingEncoder]): Embedding encoder to use.
    	pgvector_store (Optional[PgVectorStore]): Existing pgvector store to use.
    	module_registry (Optional[ModuleRegistry]): Existing module registry to use.
    	workflow_store (Optional[WorkflowStore]): Existing workflow store to use.
    	run_store (Optional[RunStore]): Existing workflow run store to use.
    	workflow_executor (Optional[WorkflowExecutor]): Existing workflow executor to use.
        workflow_dispatcher (Optional[RunDispatcher]): Scheduler used for ingestion runs.
    
    Returns:
    	APIRouter: Router exposing data-source, vector-index, database, and ingestion-job endpoints.
    """
    router = APIRouter(prefix="/data-sources", tags=["Data Sources"])

    vector_index_store = VectorIndexStore(vector_index_dir)
    embedding_artifact_store = EmbeddingArtifactStore(embedding_artifact_dir)
    pg_store = pgvector_store or PgVectorStore(PGVECTOR_URL)
    registry = module_registry or ModuleRegistry(
        repository=AnswerCacheRepository(),
        embedding_encoder=embedding_encoder,
        embedding_artifact_store=embedding_artifact_store,
        vector_index_store=vector_index_store,
        pgvector_store=pg_store,
        db_manager=DatabaseManager(),
        processed_dir=processed_dir,
        spreadsheet_artifact_dir=spreadsheet_artifact_dir,
    )
    workflow_store = workflow_store or WorkflowStore(workflow_dir)
    run_store = run_store or RunStore(run_dir, db_manager=registry.db_manager)
    workflow_executor = workflow_executor or WorkflowExecutor(
        registry,
        run_store,
        ResultCache(cache_dir),
    )
    if workflow_dispatcher is None:
        from ..orchestration.prefect import PrefectIngestionDispatcher

        workflow_dispatcher = PrefectIngestionDispatcher(
            workflow_executor,
            run_store,
            PREFECT_DEPLOYMENT_NAME,
        )
    ingestion_jobs = IngestionJobService(
        workflow_store,
        run_store,
        workflow_executor,
        workflow_dispatcher,
    )

    # Schedule recovery in a background thread to avoid blocking router creation
    import threading
    def _recover_in_background():
        try:
            recovered_jobs = ingestion_jobs.recover_pending()
            if recovered_jobs:
                logger.info("미완료 인덱싱 작업 %d개를 서버 큐에 복구했습니다", recovered_jobs)
        except Exception as error:
            logger.warning("백그라운드 run 복구 실패: %s", error)

    recovery_thread = threading.Thread(target=_recover_in_background, daemon=True)
    recovery_thread.start()

    db_manager = registry.db_manager
    # 0. Database Status
    @router.get("/db-status")
    def get_db_status() -> Dict[str, Any]:
        """Get pgvector PostgreSQL connection status and statistics."""
        return pg_store.get_db_info()

    # 0-1. Test / Update DB Connection
    @router.post("/db-connect")
    def test_db_connect(req: DbConnectRequestDTO) -> Dict[str, Any]:
        """Test a given pgvector database URL."""
        try:
            parsed = urlparse(req.database_url)
        except Exception as parse_error:
            raise HTTPException(
                status_code=400,
                detail="유효하지 않은 데이터베이스 URL입니다.",
            ) from parse_error

        scheme = (parsed.scheme or "").lower()
        if scheme not in ("postgresql", "postgresql+psycopg", "postgres"):
            raise HTTPException(
                status_code=400,
                detail="PostgreSQL 데이터베이스 URL만 지원됩니다.",
            )

        if not _is_allowed_database_host(parsed.hostname, parsed.port):
            raise HTTPException(
                status_code=400,
                detail="허용되지 않은 데이터베이스 호스트입니다.",
            )

        # Validate and store parsed values once
        safe_host = parsed.hostname or "localhost"
        safe_port = parsed.port or 5432
        safe_database = parsed.path.lstrip("/") or "rag_flow"

        # Validate port is in valid range
        if not (1 <= safe_port <= 65535):
            raise HTTPException(
                status_code=400,
                detail="유효하지 않은 포트 번호입니다.",
            )

        try:
            test_store = PgVectorStore(req.database_url)
            info = test_store.get_db_info()
            if not info.get("connected"):
                return {
                    "connected": False,
                    "host": safe_host,
                    "port": safe_port,
                    "database": safe_database,
                    "framework": "LangChain",
                    "error": "데이터베이스 연결에 실패했습니다.",
                    "total_indexes": 0,
                    "total_chunks": 0,
                }
            return info
        except Exception as err:
            logger.warning("Database connection test failed: %s", err)
            return {
                "connected": False,
                "host": safe_host,
                "port": safe_port,
                "database": safe_database,
                "framework": "LangChain",
                "error": "데이터베이스 연결에 실패했습니다.",
                "total_indexes": 0,
                "total_chunks": 0,
            }

    # 1. List files
    @router.get("/files")
    def get_files() -> Dict[str, Any]:
        """List all available raw files in data/source_files/."""
        files = list_processed_files(processed_dir, pg_store)
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
        batch_size: int = Query(default=2048, ge=1, le=2048, description="임베딩 배치 크기"),
    ) -> Dict[str, Any]:
        """
        Upload a file to processed storage and optionally submit an Excel file for ingestion.
        
        Parameters:
            auto_ingest (bool): Whether to automatically submit supported Excel files for ingestion.
            model (str): Embedding model used for automatic ingestion.
            batch_size (int): Number of items processed per embedding batch.
        
        Returns:
            Dict[str, Any]: Upload status, file metadata, optional ingestion job details, and any ingestion error.
        """
        if not file.filename:
            raise HTTPException(status_code=400, detail="유효한 파일명이 필요합니다")

        safe_filename = Path(file.filename).name
        dest_path = processed_dir / safe_filename
        temporary_path = processed_dir / (
            f".{safe_filename}.{uuid4().hex}.uploading"
        )

        try:
            processed_dir.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            size_bytes = 0
            with temporary_path.open("wb") as buffer:
                while chunk := await file.read(1024 * 1024):
                    size_bytes += len(chunk)
                    if size_bytes > MAX_UPLOAD_SIZE_BYTES:
                        raise HTTPException(
                            status_code=413,
                            detail="파일 크기는 500MB를 초과할 수 없습니다",
                        )
                    digest.update(chunk)
                    buffer.write(chunk)
            temporary_path.replace(dest_path)
            file_hash = digest.hexdigest()
        except HTTPException:
            if temporary_path.exists():
                temporary_path.unlink()
            raise
        except Exception as error:
            if temporary_path.exists():
                temporary_path.unlink()
            raise HTTPException(
                status_code=500,
                detail=f"파일 저장 실패: {error}",
            ) from error
        finally:
            await file.close()

        if db_manager.is_connected():
            try:
                db_manager.save_source_file(
                    file_id=file_hash,
                    file_name=safe_filename,
                    file_hash=file_hash,
                    file_type=dest_path.suffix.lstrip(".").lower() or "bin",
                    file_size=dest_path.stat().st_size,
                    storage_path=str(dest_path.resolve()),
                )
            except Exception as error:
                logger.warning(
                    "업로드 파일의 DB 메타데이터 저장 실패: %s",
                    error,
                )

        ingestion_job = None
        ingest_error = None
        suffix = dest_path.suffix.lower()
        if auto_ingest and suffix in (".xlsx", ".xlsm"):
            try:
                run = ingestion_jobs.create_and_submit(
                    IngestRequestDTO(
                        file_name=safe_filename,
                        model=model,
                        batch_size=batch_size,
                    )
                )
                ingestion_job = ingestion_jobs.payload(run)
            except Exception as err:
                logger.exception(
                    "업로드 후 자동 인덱싱 작업 생성 실패: %s",
                    safe_filename,
                )
                ingest_error = str(err)

        uploaded = get_processed_file_info(
            dest_path,
            workbook_hash=(
                file_hash
                if suffix in (".xlsx", ".xlsm", ".json")
                else None
            ),
        )
        return {
            "status": "success",
            "file": uploaded,
            "ingestion_job": ingestion_job,
            "error": ingest_error,
        }

    # 3-1. Download raw file from server disk storage
    @router.get("/files/{filename}/download")
    def download_file(filename: str) -> FileResponse:
        """
        Download a processed file as an attachment.
        
        Parameters:
            filename (str): Name of the processed file to download.
        
        Returns:
            FileResponse: The requested file with an attachment disposition.
        
        Raises:
            HTTPException: If the requested file does not exist.
        """
        safe_filename = Path(filename).name
        target_path = processed_dir / safe_filename

        if not target_path.is_file():
            raise HTTPException(status_code=404, detail="다운로드할 파일을 찾을 수 없습니다")

        return FileResponse(
            path=target_path,
            media_type="application/octet-stream",
            filename=safe_filename,
        )

    # 4. Delete file
    @router.delete("/files/{filename}")
    def delete_file(
        filename: str,
        cascade_indexes: bool = Query(default=True, description="연관된 벡터 인덱스도 함께 삭제(고아 벡터 방지)"),
    ) -> Dict[str, Any]:
        """
        Delete a processed source file and optionally remove its associated vector indexes.
        
        Parameters:
            filename (str): Name of the processed file to delete.
            cascade_indexes (bool): Whether to delete vector indexes associated with the file.
        
        Returns:
            Dict[str, Any]: Deletion status, sanitized filename, and count of removed vector indexes.
        """
        safe_filename = Path(filename).name
        target_path = processed_dir / safe_filename

        workbook_hash = None
        if target_path.is_file():
            workbook_hash = _sha256_file(target_path)
            target_path.unlink()

        if workbook_hash and db_manager.is_connected():
            db_manager.delete_source_file(workbook_hash)
        elif db_manager.is_connected():
            db_manager.delete_source_file(safe_filename)

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
        indexes = list_vector_indexes(pg_store)
        return {"indexes": indexes, "total": len(indexes)}

    # 6. Get index detail
    @router.get("/indexes/{index_id}")
    def get_index(index_id: str) -> Dict[str, Any]:
        """Retrieve detailed information and sample items for a vector index."""
        try:
            return get_vector_index_detail(
                index_id,
                sample_items_count=20,
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
        """
        Delete a vector index from storage.
        
        Returns:
        	dict[str, Any]: A success status and the deleted index identifier.
        
        Raises:
        	HTTPException: With status 404 if the index does not exist, or 500 if deletion fails.
        """
        try:
            deleted = delete_vector_index(index_id, pg_store)
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
        """
        Perform a similarity search against a vector index.
        
        Parameters:
            request (SearchRequestDTO): Search query and result limit.
        
        Returns:
            Dict[str, Any]: Search response containing the index ID, query, matching results, and result count.
        
        Raises:
            HTTPException: If the search fails.
        """
        try:
            hits = search_vector_index(
                index_id,
                query_text=request.query,
                limit=request.limit,
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

    # 9. Create a persistent, server-owned ingestion workflow job
    @router.get("/ingestion-jobs")
    def list_ingestion_jobs(
        file_name: Optional[str] = Query(default=None),
        limit: int = Query(default=20, ge=1, le=100),
    ) -> Dict[str, Any]:
        """
        List persisted ingestion jobs, optionally filtered by source filename.
        
        Parameters:
            file_name (Optional[str]): Source filename used to filter jobs.
            limit (int): Maximum number of jobs to include.
        
        Returns:
            Dict[str, Any]: A mapping containing the selected jobs and the total number of matching jobs.
        """
        candidates = ingestion_jobs.list(file_name)
        selected = candidates[:limit]
        return {
            "jobs": [
                ingestion_jobs.payload(summary, include_index=False)
                for summary in selected
            ],
            "total": len(candidates),
        }

    @router.post("/ingestion-jobs", status_code=202)
    def create_ingestion_job(request: IngestRequestDTO) -> Dict[str, Any]:
        """
        Create and submit a persistent ingestion job for the requested source file.
        
        Parameters:
            request (IngestRequestDTO): Ingestion configuration and source file details.
        
        Returns:
            Dict[str, Any]: Public representation of the submitted ingestion job.
        
        Raises:
            HTTPException: If the ingestion workflow is missing or the request is invalid.
        """
        try:
            run = ingestion_jobs.create_and_submit(request)
            return ingestion_jobs.payload(run)
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail=f"인덱싱 워크플로를 찾을 수 없습니다: {error}",
            ) from error
        except (DagExecutionError, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.get("/ingestion-jobs/{run_id}")
    def get_ingestion_job(run_id: str) -> Dict[str, Any]:
        """
        Retrieve the public status and details of an ingestion job.
        
        Parameters:
            run_id (str): Identifier of the ingestion job.
        
        Returns:
            Dict[str, Any]: Sanitized job status, metadata, execution state, and results.
        
        Raises:
            HTTPException: With status 404 if the job does not exist, or 422 if the job is invalid.
        """
        try:
            run = ingestion_jobs.load_status(run_id)
            ingestion_jobs.ensure_submitted(run)
            return ingestion_jobs.payload(run)
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail="인덱싱 작업을 찾을 수 없습니다",
            ) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.get("/ingestion-jobs/by-index/{index_id}")
    def get_ingestion_job_by_index(index_id: str) -> Dict[str, Any]:
        """
        Finds the ingestion job that produced the specified index.
        
        Parameters:
            index_id (str): Identifier of the pgvector index.
        
        Returns:
            Dict[str, Any]: Public representation of the matching ingestion job.
        
        Raises:
            HTTPException: If no ingestion job produced the specified index.
        """
        try:
            return ingestion_jobs.payload(ingestion_jobs.find_by_index(index_id))
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail="해당 인덱스의 워크플로 실행 기록을 찾을 수 없습니다",
            ) from error

    @router.post("/ingestion-jobs/{run_id}/resume", status_code=202)
    def resume_ingestion_job(run_id: str) -> Dict[str, Any]:
        """
        Resume an ingestion job according to its current state.
        
        Parameters:
            run_id (str): Identifier of the ingestion job to resume.
        
        Returns:
            Dict[str, Any]: Updated public representation of the ingestion job.
        
        Raises:
            HTTPException: With status code 404 if the ingestion job does not exist.
        """
        try:
            run = ingestion_jobs.load(run_id)
            if run.status == "completed":
                raise HTTPException(
                    status_code=409,
                    detail="완료된 인덱싱 작업은 재개할 수 없습니다",
                )
            return ingestion_jobs.payload(ingestion_jobs.resume(run_id))
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail="인덱싱 작업을 찾을 수 없습니다",
            ) from error

    @router.post("/ingestion-jobs/{run_id}/cancel")
    def cancel_ingestion_job(run_id: str) -> Dict[str, Any]:
        """
        Cancel an ingestion job and return its updated state.
        
        Parameters:
            run_id (str): Identifier of the ingestion job to cancel.
        
        Returns:
            Dict[str, Any]: The updated public job representation.
        
        Raises:
            HTTPException: If the ingestion job does not exist.
        """
        try:
            return ingestion_jobs.payload(ingestion_jobs.cancel(run_id))
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail="인덱싱 작업을 찾을 수 없습니다",
            ) from error

    @router.delete("/ingestion-jobs/{run_id}")
    def delete_ingestion_job(run_id: str) -> Dict[str, Any]:
        """
        Stop and remove an ingestion job and delete its associated vector index when present.
        
        Parameters:
            run_id (str): Identifier of the ingestion job to remove.
        
        Returns:
            Dict[str, Any]: Deletion status, job identifier, target index identifier,
                index deletion status, and confirmation that the source file was preserved.
        """

        try:
            run = ingestion_jobs.load(run_id)
            if run.status in ("queued", "running"):
                run = ingestion_jobs.cancel(run_id)
            target_index_id = ingestion_jobs.target_index_id(run)
            index_deleted = False
            if target_index_id:
                try:
                    target_exists = any(
                        index.get("index_id") == target_index_id
                        for index in pg_store.list_indexes()
                    )
                except Exception as error:
                    raise HTTPException(
                        status_code=503,
                        detail=(
                            "부분 컬렉션 존재 여부를 확인하지 못해 작업 기록을 "
                            "보존했습니다"
                        ),
                    ) from error
                if target_exists:
                    if not pg_store.delete(target_index_id):
                        raise HTTPException(
                            status_code=500,
                            detail=(
                                "부분 컬렉션 삭제에 실패해 작업 기록을 보존했습니다"
                            ),
                        )
                    index_deleted = True
            if not run_store.delete(run_id):
                raise FileNotFoundError(run_id)
            return {
                "status": "deleted",
                "job_id": run_id,
                "target_index_id": target_index_id,
                "index_deleted": index_deleted,
                "source_file_preserved": True,
            }
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail="삭제할 인덱싱 작업을 찾을 수 없습니다",
            ) from error

    return router
