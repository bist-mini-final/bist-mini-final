"""HTTP adapter for persistent Excel ingestion jobs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi import Path as FastPath

from backend.engine.workflows import DagExecutionError, RunStore
from backend.storage.data_sources import IngestionJobService
from backend.storage.data_sources import IngestionRequest as IngestRequestDTO
from backend.storage.pgvector_store import PgVectorStore


def create_ingestion_router(
    ingestion_jobs: IngestionJobService,
    run_store: RunStore,
    pgvector_store: PgVectorStore,
) -> APIRouter:
    """엑셀 인덱싱 비동기 작업 관리를 위한 FastAPI 라우터 생성."""
    router = APIRouter()

    @router.get(
        "/ingestion-jobs",
        summary="스프레드시트 인덱싱 작업 목록 조회",
        description="등록된 엑셀 인덱싱 작업 목록, 실행 상태, 대상 파일 및 완료 여부를 조회합니다.",
    )
    def list_ingestion_jobs(
        file_name: str | None = Query(default=None, description="특정 파일명 필터"),
        limit: int = Query(default=20, ge=1, le=100, description="반환할 최대 작업 수"),
    ) -> dict[str, Any]:
        """등록된 스프레드시트 인덱싱 작업 목록을 반환합니다."""
        candidates = ingestion_jobs.list(file_name)
        return {
            "jobs": [
                ingestion_jobs.payload(summary, include_index=False)
                for summary in candidates[:limit]
            ],
            "total": len(candidates),
        }

    @router.post(
        "/ingestion-jobs",
        status_code=202,
        summary="새로운 스프레드시트 인덱싱 작업 생성 및 큐 등록",
        description="업로드된 엑셀 파일에 대해 Luna VLM 구조 감지 및 pgvector 인덱싱 DAG를 큐에 등록합니다.",
    )
    def create_ingestion_job(request: IngestRequestDTO) -> dict[str, Any]:
        """새로운 스프레드시트 인덱싱 작업을 생성하고 큐에 제출합니다."""
        try:
            return ingestion_jobs.payload(
                ingestion_jobs.create_and_submit(request)
            )
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail=f"인덱싱 워크플로를 찾을 수 없습니다: {error}",
            ) from error
        except (DagExecutionError, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @router.get(
        "/ingestion-jobs/{run_id}",
        summary="단일 인덱싱 작업 진행 상태 조회",
        description="지정된 실행 ID(`run_id`)의 인덱싱 작업 진행률 및 상태를 조회합니다.",
    )
    def get_ingestion_job(
        run_id: str = FastPath(..., description="인덱싱 실행 ID"),
    ) -> dict[str, Any]:
        """단일 인덱싱 작업의 진행 상태와 결과 페이로드를 반환합니다."""
        try:
            return ingestion_jobs.payload(ingestion_jobs.load_status(run_id))
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail="인덱싱 작업을 찾을 수 없습니다",
            ) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @router.get(
        "/ingestion-jobs/by-index/{index_id}",
        summary="인덱스 ID 기준 인덱싱 작업 조회",
        description="생성된 pgvector 인덱스 ID를 통해 연관된 원본 인덱싱 워크플로 실행 기록을 조회합니다.",
    )
    def get_ingestion_job_by_index(
        index_id: str = FastPath(..., description="pgvector 인덱스 컬렉션 ID"),
    ) -> dict[str, Any]:
        """pgvector 인덱스 컬렉션 ID에 바인딩된 인덱싱 작업 정보를 반환합니다."""
        try:
            return ingestion_jobs.payload(ingestion_jobs.find_by_index(index_id))
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail="해당 인덱스의 워크플로 실행 기록을 찾을 수 없습니다",
            ) from error

    @router.post(
        "/ingestion-jobs/{run_id}/resume",
        status_code=202,
        summary="실패한 인덱싱 작업 재개",
        description="중단되거나 실패한 인덱싱 작업을 실패 노드부터 다시 시작합니다.",
    )
    def resume_ingestion_job(
        run_id: str = FastPath(..., description="재개할 인덱싱 실행 ID"),
    ) -> dict[str, Any]:
        """실패하거나 일시 중지된 인덱싱 작업을 재개합니다."""
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
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @router.post(
        "/ingestion-jobs/{run_id}/cancel",
        summary="진행 중인 인덱싱 작업 취소",
        description="실행 대기 중이거나 진행 중인 인덱싱 작업을 중단합니다.",
    )
    def cancel_ingestion_job(
        run_id: str = FastPath(..., description="취소할 인덱싱 실행 ID"),
    ) -> dict[str, Any]:
        """진행 중인 인덱싱 작업을 취소합니다."""
        try:
            return ingestion_jobs.payload(ingestion_jobs.cancel(run_id))
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail="인덱싱 작업을 찾을 수 없습니다",
            ) from error
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @router.delete(
        "/ingestion-jobs/{run_id}",
        summary="인덱싱 작업 기록 삭제",
        description="인덱싱 작업 실행 기록을 삭제하고 미완성된 임시 인덱스 컬렉션을 정리합니다.",
    )
    def delete_ingestion_job(
        run_id: str = FastPath(..., description="삭제할 인덱싱 실행 ID"),
    ) -> dict[str, Any]:
        """인덱싱 작업 실행 기록을 삭제합니다."""
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
                        for index in pgvector_store.list_indexes()
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
                    if not pgvector_store.delete(target_index_id):
                        raise HTTPException(
                            status_code=500,
                            detail="부분 컬렉션 삭제에 실패해 작업 기록을 보존했습니다",
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


__all__ = ["create_ingestion_router"]
