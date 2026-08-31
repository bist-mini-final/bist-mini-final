"""Presentation controller for durable spreadsheet ingestion jobs."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from backend.domains.data_sources.application.ingestion_jobs import (
    IngestionJobService,
)
from backend.domains.data_sources.application.ingestion_jobs import (
    IngestionRequest as IngestRequestDTO,
)
from backend.domains.data_sources.application.ports import (
    DataSourceCatalogPort,
    IngestionRunRepository,
)
from backend.domains.workflow.domain import DagExecutionError


class IngestionHttpController:
    """Translate ingestion application outcomes into stable HTTP responses."""

    def __init__(
        self,
        ingestion_jobs: IngestionJobService,
        run_store: IngestionRunRepository,
        catalog: DataSourceCatalogPort,
    ) -> None:
        self._jobs = ingestion_jobs
        self._runs = run_store
        self._catalog = catalog

    def list_jobs(self, file_name: str | None, limit: int) -> dict[str, Any]:
        candidates = self._jobs.list(file_name)
        return {
            "jobs": [
                self._jobs.payload(summary, include_index=False) for summary in candidates[:limit]
            ],
            "total": len(candidates),
        }

    def create_job(self, request: IngestRequestDTO) -> dict[str, Any]:
        try:
            return self._jobs.payload(self._jobs.create_and_submit(request))
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail=f"인덱싱 워크플로를 찾을 수 없습니다: {error}",
            ) from error
        except (DagExecutionError, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    def get_job(self, run_id: str) -> dict[str, Any]:
        try:
            return self._jobs.payload(self._jobs.load_status(run_id))
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="인덱싱 작업을 찾을 수 없습니다") from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    def get_job_by_index(self, index_id: str) -> dict[str, Any]:
        try:
            return self._jobs.payload(self._jobs.find_by_index(index_id))
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail="해당 인덱스의 워크플로 실행 기록을 찾을 수 없습니다",
            ) from error

    def resume_job(self, run_id: str) -> dict[str, Any]:
        try:
            run = self._jobs.load(run_id)
            if run.status == "completed":
                raise HTTPException(
                    status_code=409,
                    detail="완료된 인덱싱 작업은 재개할 수 없습니다",
                )
            return self._jobs.payload(self._jobs.resume(run_id))
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="인덱싱 작업을 찾을 수 없습니다") from error
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    def cancel_job(self, run_id: str) -> dict[str, Any]:
        try:
            return self._jobs.payload(self._jobs.cancel(run_id))
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="인덱싱 작업을 찾을 수 없습니다") from error
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    def _delete_partial_index(self, index_id: str | None) -> bool:
        if not index_id:
            return False
        try:
            exists = any(
                index.get("index_id") == index_id for index in self._catalog.list_indexes()
            )
        except Exception as error:
            raise HTTPException(
                status_code=503,
                detail="부분 컬렉션 존재 여부를 확인하지 못해 작업 기록을 보존했습니다",
            ) from error
        if exists and not self._catalog.delete_index(index_id):
            raise HTTPException(
                status_code=500,
                detail="부분 컬렉션 삭제에 실패해 작업 기록을 보존했습니다",
            )
        return exists

    def delete_job(self, run_id: str) -> dict[str, Any]:
        try:
            run = self._jobs.load(run_id)
            if run.status in ("queued", "running"):
                run = self._jobs.cancel(run_id)
            target_index_id = self._jobs.target_index_id(run)
            index_deleted = self._delete_partial_index(target_index_id)
            if not self._runs.delete(run_id):
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


__all__ = ["IngestionHttpController"]
