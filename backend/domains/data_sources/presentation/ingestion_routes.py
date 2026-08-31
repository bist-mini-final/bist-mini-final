"""HTTP route declarations for persistent Excel ingestion jobs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from fastapi import Path as FastPath

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

from .ingestion_controller import IngestionHttpController


def create_ingestion_router(
    ingestion_jobs: IngestionJobService,
    run_store: IngestionRunRepository,
    catalog: DataSourceCatalogPort,
) -> APIRouter:
    """Declare ingestion endpoints over a focused presentation controller."""
    router = APIRouter()
    controller = IngestionHttpController(ingestion_jobs, run_store, catalog)

    @router.get(
        "/ingestion-jobs",
        summary="스프레드시트 인덱싱 작업 목록 조회",
        description="등록된 엑셀 인덱싱 작업 목록, 실행 상태, 대상 파일 및 완료 여부를 조회합니다.",
    )
    def list_ingestion_jobs(
        file_name: str | None = Query(default=None, description="특정 파일명 필터"),
        limit: int = Query(default=20, ge=1, le=100, description="반환할 최대 작업 수"),
    ) -> dict[str, Any]:
        return controller.list_jobs(file_name, limit)

    @router.post(
        "/ingestion-jobs",
        status_code=202,
        summary="새로운 스프레드시트 인덱싱 작업 생성 및 큐 등록",
        description="업로드된 엑셀 파일에 대해 Luna VLM 구조 감지 및 pgvector 인덱싱 DAG를 큐에 등록합니다.",
    )
    def create_ingestion_job(request: IngestRequestDTO) -> dict[str, Any]:
        return controller.create_job(request)

    @router.get(
        "/ingestion-jobs/{run_id}",
        summary="단일 인덱싱 작업 진행 상태 조회",
        description="지정된 실행 ID의 인덱싱 작업 진행률 및 상태를 조회합니다.",
    )
    def get_ingestion_job(
        run_id: str = FastPath(..., description="인덱싱 실행 ID"),
    ) -> dict[str, Any]:
        return controller.get_job(run_id)

    @router.get(
        "/ingestion-jobs/by-index/{index_id}",
        summary="인덱스 ID 기준 인덱싱 작업 조회",
        description="생성된 pgvector 인덱스 ID로 연관된 원본 인덱싱 실행 기록을 조회합니다.",
    )
    def get_ingestion_job_by_index(
        index_id: str = FastPath(..., description="pgvector 인덱스 컬렉션 ID"),
    ) -> dict[str, Any]:
        return controller.get_job_by_index(index_id)

    @router.post(
        "/ingestion-jobs/{run_id}/resume",
        status_code=202,
        summary="실패한 인덱싱 작업 재개",
        description="중단되거나 실패한 인덱싱 작업을 실패 노드부터 다시 시작합니다.",
    )
    def resume_ingestion_job(
        run_id: str = FastPath(..., description="재개할 인덱싱 실행 ID"),
    ) -> dict[str, Any]:
        return controller.resume_job(run_id)

    @router.post(
        "/ingestion-jobs/{run_id}/cancel",
        summary="진행 중인 인덱싱 작업 취소",
        description="실행 대기 중이거나 진행 중인 인덱싱 작업을 중단합니다.",
    )
    def cancel_ingestion_job(
        run_id: str = FastPath(..., description="취소할 인덱싱 실행 ID"),
    ) -> dict[str, Any]:
        return controller.cancel_job(run_id)

    @router.delete(
        "/ingestion-jobs/{run_id}",
        summary="인덱싱 작업 기록 삭제",
        description="실행 기록을 삭제하고 미완성된 임시 인덱스 컬렉션을 정리합니다.",
    )
    def delete_ingestion_job(
        run_id: str = FastPath(..., description="삭제할 인덱싱 실행 ID"),
    ) -> dict[str, Any]:
        return controller.delete_job(run_id)

    return router


__all__ = ["create_ingestion_router"]
