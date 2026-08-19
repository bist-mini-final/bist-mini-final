"""API router for Data Sources (Files & Vector Indexes & pgvector DB)."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..core.settings import (
    EMBEDDING_ARTIFACT_DIR,
    PGVECTOR_URL,
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
    ResultCache,
    RunStore,
    WorkflowExecutionRequest,
    WorkflowExecutor,
    WorkflowRun,
    WorkflowRunDispatcher,
    WorkflowStore,
)


INGESTION_WORKFLOW_IDS = frozenset(
    {"indexing_pgvector", "indexing_pgvector_exhaustive"}
)
MAX_UPLOAD_SIZE_BYTES = 500 * 1024 * 1024
logger = logging.getLogger(__name__)


def _public_error(value: Optional[str], limit: int = 2000) -> Optional[str]:
    """
    Sanitizes an error message for public responses.
    
    Parameters:
        value (Optional[str]): The error message to sanitize.
        limit (int): Maximum length of the returned message.
    
    Returns:
        Optional[str]: The sanitized message, or `None` when `value` is `None`.
    """
    if value is None:
        return None
    message = value
    for marker in ("\n[SQL:", " [SQL:"):
        if marker in message:
            message = message.split(marker, 1)[0].rstrip()
            break
    return message if len(message) <= limit else message[:limit].rstrip() + "…"


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


class IngestRequestDTO(BaseModel):
    file_name: str = Field(min_length=1, description="data/processed/ 내 대상 Excel 파일명")
    model: str = Field(
        default="text-embedding-3-large",
        description="임베딩 모델 (예: text-embedding-3-large, BAAI/bge-large-en-v1.5)",
    )
    variant_mode: Literal["header_only", "header_with_value", "both"] = Field(
        default="both",
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
        default=2048,
        ge=1,
        le=2048,
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
    workflow_dir: Path = WORKFLOW_DIR,
    run_dir: Path = RUN_DIR,
    cache_dir: Path = CACHE_DIR,
    embedding_encoder: Optional[EmbeddingEncoder] = None,
    pgvector_store: Optional[PgVectorStore] = None,
    module_registry: Optional[ModuleRegistry] = None,
    workflow_store: Optional[WorkflowStore] = None,
    run_store: Optional[RunStore] = None,
    workflow_executor: Optional[WorkflowExecutor] = None,
    workflow_dispatcher: Optional[WorkflowRunDispatcher] = None,
) -> APIRouter:
    """
    Create the data-source API router and configure its file, vector-index, database, and ingestion workflow dependencies.
    
    Parameters:
        processed_dir (Path): Directory containing uploaded source files.
        vector_index_dir (Path): Directory used for vector-index artifacts.
        embedding_artifact_dir (Path): Directory containing embedding artifacts.
        spreadsheet_artifact_dir (Path): Directory containing spreadsheet artifacts.
        workflow_dir (Path): Directory containing workflow definitions.
        run_dir (Path): Directory for persisted workflow runs.
        cache_dir (Path): Directory for cached workflow results.
        embedding_encoder (Optional[EmbeddingEncoder]): Encoder used for embedding operations.
        pgvector_store (Optional[PgVectorStore]): Existing pgvector store to use.
        module_registry (Optional[ModuleRegistry]): Existing module registry to use.
        workflow_store (Optional[WorkflowStore]): Existing workflow store to use.
        run_store (Optional[RunStore]): Existing workflow run store to use.
        workflow_executor (Optional[WorkflowExecutor]): Existing workflow executor to use.
        workflow_dispatcher (Optional[WorkflowRunDispatcher]): Existing workflow dispatcher to use.
    
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
    run_store = run_store or RunStore(run_dir)
    workflow_executor = workflow_executor or WorkflowExecutor(
        registry,
        run_store,
        ResultCache(cache_dir),
    )
    workflow_dispatcher = workflow_dispatcher or WorkflowRunDispatcher(
        workflow_executor,
        run_store,
    )
    recovered_jobs = workflow_dispatcher.recover_pending(INGESTION_WORKFLOW_IDS)
    if recovered_jobs:
        logger.info("미완료 인덱싱 작업 %d개를 서버 큐에 복구했습니다", recovered_jobs)
    db_manager = registry.db_manager

    def _workflow_id_for(request: IngestRequestDTO) -> str:
        """Selects the pgvector ingestion workflow for the requested structure mode.
        
        Parameters:
        	request (IngestRequestDTO): Ingestion request containing the structure mode.
        
        Returns:
        	str: The exhaustive pgvector workflow identifier for exhaustive mode; otherwise, the standard pgvector workflow identifier.
        """
        if request.structure_mode == "exhaustive":
            return "indexing_pgvector_exhaustive"
        return "indexing_pgvector"

    def _create_ingestion_run(request: IngestRequestDTO) -> WorkflowRun:
        """
        Create a cached workflow run for the requested ingestion operation.
        
        Parameters:
            request (IngestRequestDTO): Ingestion settings, including the source file,
                optional sheets, embedding model, serialization mode, and batch size.
        
        Returns:
            WorkflowRun: The newly created ingestion workflow run.
        
        Raises:
            DagExecutionError: If the workflow lacks a processed file selector or
                pgvector index writer.
        """
        workflow = workflow_store.load(_workflow_id_for(request))
        runtime_inputs: Dict[str, Dict[str, Any]] = {}
        config_overrides: Dict[str, Dict[str, Any]] = {}
        has_writer = False

        for node in workflow.graph.nodes:
            if node.module_type == "processed_file_selector":
                selector_input: Dict[str, Any] = {"file_name": request.file_name}
                if request.sheet_names is not None:
                    selector_input["sheet_names"] = request.sheet_names
                runtime_inputs[node.id] = selector_input
            elif node.module_type in {
                "cell_text_serializer",
                "exhaustive_cell_text_serializer",
            }:
                config_overrides[node.id] = {
                    "variant_mode": request.variant_mode,
                }
            elif node.module_type == "cell_text_embedder":
                config_overrides[node.id] = {
                    "model": request.model,
                    "batch_size": request.batch_size,
                }
            elif node.module_type == "pgvector_index_writer":
                has_writer = True

        if not runtime_inputs:
            raise DagExecutionError(
                "인덱싱 워크플로에 processed_file_selector 모듈이 없습니다"
            )
        if not has_writer:
            raise DagExecutionError(
                "인덱싱 워크플로에 pgvector_index_writer 모듈이 없습니다"
            )

        return workflow_executor.create_run(
            workflow,
            WorkflowExecutionRequest(
                inputs=runtime_inputs,
                config_overrides=config_overrides,
                use_cache=True,
            ),
        )

    def _node_output(run: WorkflowRun, module_type: str) -> Optional[Dict[str, Any]]:
        """
        Finds the dictionary output produced by the first node of the specified module type.
        
        Parameters:
        	run (WorkflowRun): The workflow run containing the node outputs.
        	module_type (str): The module type to locate.
        
        Returns:
        	Optional[Dict[str, Any]]: The matching node's dictionary output, or `None` if no matching dictionary output exists.
        """
        for node in run.graph.nodes:
            if node.module_type != module_type:
                continue
            output = run.nodes[node.id].output
            if isinstance(output, dict):
                return output
        return None

    def _target_index_id(run: WorkflowRun) -> Optional[str]:
        """
        Determine the vector index identifier associated with a workflow run.
        
        Parameters:
        	run (WorkflowRun): The ingestion workflow run to inspect.
        
        Returns:
        	Optional[str]: The target vector index identifier, or `None` when no identifier is available.
        """
        writer_output = _node_output(run, "pgvector_index_writer") or {}
        if isinstance(writer_output.get("index_id"), str):
            return writer_output["index_id"]
        writer_node = next(
            (
                node
                for node in run.graph.nodes
                if node.module_type == "pgvector_index_writer"
            ),
            None,
        )
        if writer_node is not None:
            target = run.nodes[writer_node.id].progress.get("target_index_id")
            if isinstance(target, str):
                return target
        embedder_output = _node_output(run, "cell_text_embedder") or {}
        artifact_id = embedder_output.get("artifact_id")
        if isinstance(artifact_id, str):
            return VectorIndexStore.index_id(artifact_id)
        return None

    def _job_payload(
        run: WorkflowRun,
        *,
        include_index: bool = True,
    ) -> Dict[str, Any]:
        """
        Build a sanitized public representation of an ingestion workflow run.
        
        Parameters:
            run (WorkflowRun): Workflow run to represent.
            include_index (bool): Whether to include details produced by the vector index writer.
        
        Returns:
            Dict[str, Any]: Job payload containing run status, sanitized node state, structure output, index details when requested, target index identifier, error information, and worker activity.
        """
        selector_output = _node_output(run, "processed_file_selector") or {}
        structure_output = _node_output(run, "luna_vlm_structure_detector")
        luna_output = None
        if structure_output is not None:
            luna_output = {
                **structure_output,
                "file_name": structure_output.get("file_name")
                or selector_output.get("file_name"),
                "workbook_hash": structure_output.get("workbook_hash")
                or selector_output.get("workbook_hash"),
                "sheet_names": selector_output.get("sheet_names", []),
            }

        index = None
        if include_index:
            writer_output = _node_output(run, "pgvector_index_writer")
            embedder_output = _node_output(run, "cell_text_embedder") or {}
            company_output = _node_output(run, "company_entity_extractor") or {}
            if writer_output is not None:
                index = {
                    **writer_output,
                    "company_name": company_output.get("display_name")
                    or company_output.get("company_name"),
                    "ticker": company_output.get("ticker"),
                    "duration_seconds": embedder_output.get("duration_seconds"),
                    "total_tokens": embedder_output.get("total_tokens"),
                    "estimated_cost_usd": embedder_output.get("estimated_cost_usd"),
                    "estimated_cost_krw": embedder_output.get("estimated_cost_krw"),
                    "batch_size": embedder_output.get("batch_size"),
                    "sheet_names": selector_output.get("sheet_names", []),
                    "tables": (structure_output or {}).get("tables", []),
                    "luna_output": luna_output,
                    "storage": "pgvector (LangChain)",
                }
        failed_state = next(
            (state for state in run.nodes.values() if state.status == "failed"),
            None,
        )
        run_summary = run.model_dump(mode="json")
        for state in run_summary["nodes"].values():
            state["input_payload"] = None
            state["output"] = None
            state["error"] = _public_error(state.get("error"))
        return {
            "job_id": run.id,
            "status": run.status,
            "workflow_id": run.workflow_id,
            "run": run_summary,
            "index": index,
            # Structure inspection is a module result, not an index-writer
            # result. Expose it as soon as Luna finishes so a long embedding
            # batch does not leave the inspector with fabricated empty data.
            "luna_output": luna_output,
            "target_index_id": _target_index_id(run),
            "error": _public_error(
                failed_state.error if failed_state is not None else None
            ),
            "worker_active": workflow_dispatcher.is_active(run.id),
        }

    def _load_ingestion_run(run_id: str) -> WorkflowRun:
        """
        Load an ingestion workflow run by its identifier.
        
        Parameters:
        	run_id (str): Identifier of the workflow run.
        
        Returns:
        	WorkflowRun: The matching ingestion workflow run.
        
        Raises:
        	FileNotFoundError: If the run does not exist or belongs to a different workflow.
        """
        run = run_store.load(run_id)
        if run.workflow_id not in INGESTION_WORKFLOW_IDS:
            raise FileNotFoundError(run_id)
        return run

    def _list_ingestion_runs(
        file_name: Optional[str] = None,
    ) -> List[WorkflowRun]:
        """
        List ingestion workflow runs, optionally filtered by source file name.
        
        Parameters:
            file_name (Optional[str]): Source file name used to filter runs. Directory components are ignored.
        
        Returns:
            List[WorkflowRun]: Ingestion runs sorted by most recently updated.
        """
        summaries = [
            run
            for run in run_store.list()
            if run.workflow_id in INGESTION_WORKFLOW_IDS
        ]
        if file_name is not None:
            safe_file_name = Path(file_name).name
            runs: List[WorkflowRun] = []
            for summary in summaries:
                if any(
                    node.module_type == "processed_file_selector"
                    and summary.runtime_inputs.get(node.id, {}).get("file_name")
                    == safe_file_name
                    for node in summary.graph.nodes
                ):
                    runs.append(run_store.load(summary.id))
        else:
            runs = summaries
        return sorted(runs, key=lambda run: run.updated_at, reverse=True)

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
                run = _create_ingestion_run(
                    IngestRequestDTO(
                        file_name=safe_filename,
                        model=model,
                        batch_size=batch_size,
                    )
                )
                workflow_dispatcher.submit(run.id)
                ingestion_job = _job_payload(run)
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
        candidates = _list_ingestion_runs(file_name)
        selected = candidates[:limit]
        return {
            "jobs": [
                _job_payload(summary, include_index=False)
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
            run = _create_ingestion_run(request)
            workflow_dispatcher.submit(run.id)
            return _job_payload(run)
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
            run = _load_ingestion_run(run_id)
            workflow_dispatcher.ensure_submitted(run_id, run)
            return _job_payload(_load_ingestion_run(run_id))
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
        for summary in _list_ingestion_runs():
            writer_output = _node_output(summary, "pgvector_index_writer")
            if writer_output and writer_output.get("index_id") == index_id:
                run = run_store.load(summary.id)
                return _job_payload(run)
        raise HTTPException(
            status_code=404,
            detail="해당 인덱스의 워크플로 실행 기록을 찾을 수 없습니다",
        )

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
            run = _load_ingestion_run(run_id)
            if run.status == "completed":
                raise HTTPException(
                    status_code=409,
                    detail="완료된 인덱싱 작업은 재개할 수 없습니다",
                )
            if run.status == "failed":
                workflow_dispatcher.submit(run_id, resume_failed=True)
            elif run.status in ("queued", "running", "paused"):
                workflow_dispatcher.submit(run_id)
            return _job_payload(run_store.load(run_id))
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
            _load_ingestion_run(run_id)
            workflow_dispatcher.cancel(run_id)
            return _job_payload(_load_ingestion_run(run_id))
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
            run = _load_ingestion_run(run_id)
            if run.status in ("queued", "running"):
                workflow_dispatcher.cancel(run_id)
                run = _load_ingestion_run(run_id)
            target_index_id = _target_index_id(run)
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
