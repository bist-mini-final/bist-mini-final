"""HTTP adapter for persistent Excel ingestion jobs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.engine.workflows import DagExecutionError, RunStore
from backend.storage.data_sources import IngestionJobService
from backend.storage.data_sources import IngestionRequest as IngestRequestDTO
from backend.storage.pgvector_store import PgVectorStore


def create_ingestion_router(
    ingestion_jobs: IngestionJobService,
    run_store: RunStore,
    pgvector_store: PgVectorStore,
) -> APIRouter:
    router = APIRouter()

    @router.get("/ingestion-jobs")
    def list_ingestion_jobs(
        file_name: str | None = Query(default=None),
        limit: int = Query(default=20, ge=1, le=100),
    ) -> dict[str, Any]:
        candidates = ingestion_jobs.list(file_name)
        return {
            "jobs": [
                ingestion_jobs.payload(summary, include_index=False)
                for summary in candidates[:limit]
            ],
            "total": len(candidates),
        }

    @router.post("/ingestion-jobs", status_code=202)
    def create_ingestion_job(request: IngestRequestDTO) -> dict[str, Any]:
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

    @router.get("/ingestion-jobs/{run_id}")
    def get_ingestion_job(run_id: str) -> dict[str, Any]:
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

    @router.get("/ingestion-jobs/by-index/{index_id}")
    def get_ingestion_job_by_index(index_id: str) -> dict[str, Any]:
        try:
            return ingestion_jobs.payload(ingestion_jobs.find_by_index(index_id))
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail="해당 인덱스의 워크플로 실행 기록을 찾을 수 없습니다",
            ) from error

    @router.post("/ingestion-jobs/{run_id}/resume", status_code=202)
    def resume_ingestion_job(run_id: str) -> dict[str, Any]:
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

    @router.post("/ingestion-jobs/{run_id}/cancel")
    def cancel_ingestion_job(run_id: str) -> dict[str, Any]:
        try:
            return ingestion_jobs.payload(ingestion_jobs.cancel(run_id))
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail="인덱싱 작업을 찾을 수 없습니다",
            ) from error
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @router.delete("/ingestion-jobs/{run_id}")
    def delete_ingestion_job(run_id: str) -> dict[str, Any]:
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
