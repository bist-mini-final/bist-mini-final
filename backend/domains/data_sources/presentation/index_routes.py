"""HTTP route declarations for vector-index management."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter
from fastapi import Path as FastPath

from .controller import (
    DataSourceHttpController,
    SearchRequestDTO,
    UpdateIndexCompanyRequestDTO,
)


def create_data_source_index_router(controller: DataSourceHttpController) -> APIRouter:
    """Declare vector-index endpoints over the data-source controller."""
    router = APIRouter()

    @router.get(
        "/indexes",
        summary="생성된 pgvector 벡터 인덱스 컬렉션 목록 조회",
    )
    def get_indexes() -> Dict[str, Any]:
        return controller.list_indexes()

    @router.get(
        "/indexes/{index_id}",
        summary="단일 pgvector 벡터 인덱스 상세 정보 조회",
    )
    def get_index_detail(
        index_id: str = FastPath(..., description="pgvector 컬렉션 ID"),
    ) -> Dict[str, Any]:
        return controller.get_index(index_id)

    @router.put(
        "/indexes/{index_id}/company",
        summary="벡터 인덱스 바인딩 기업명 수정",
    )
    def update_index_company(
        index_id: str = FastPath(..., description="수정할 pgvector 컬렉션 ID"),
        body: UpdateIndexCompanyRequestDTO = None,  # type: ignore[assignment]
    ) -> Dict[str, Any]:
        return controller.update_index_company(index_id, body)

    @router.delete(
        "/indexes/{index_id}",
        summary="pgvector 벡터 인덱스 컬렉션 삭제",
    )
    def remove_index(
        index_id: str = FastPath(..., description="삭제할 pgvector 컬렉션 ID"),
    ) -> Dict[str, Any]:
        return controller.delete_index(index_id)

    @router.post(
        "/indexes/{index_id}/search",
        summary="단일 벡터 인덱스 대상 즉시 유사도 검색 테스트",
    )
    def search_index(
        index_id: str = FastPath(..., description="검색 대상 pgvector 컬렉션 ID"),
        body: SearchRequestDTO = None,  # type: ignore[assignment]
    ) -> Dict[str, Any]:
        return controller.search_index(index_id, body)

    return router


__all__ = ["create_data_source_index_router"]
