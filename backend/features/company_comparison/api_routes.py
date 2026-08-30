"""HTTP adapter for the company-comparison snapshot."""

from typing import Any

from fastapi import APIRouter, HTTPException
from starlette import status

from backend.contracts import ApiErrorEnvelope

from .errors import ComparisonDataError
from .models import CompanyComparisonSnapshot
from .service import CompanyComparisonService


def create_company_comparison_router(
    service: CompanyComparisonService,
    *,
    prefix: str = "/company-comparisons",
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=["기업 비교"])
    error_responses: dict[int | str, dict[str, Any]] = {
        404: {"model": ApiErrorEnvelope},
        409: {"model": ApiErrorEnvelope},
        500: {"model": ApiErrorEnvelope},
        503: {"model": ApiErrorEnvelope},
    }

    @router.get(
        "/snapshot",
        response_model=CompanyComparisonSnapshot,
        responses=error_responses,
    )
    async def get_company_comparison_snapshot() -> CompanyComparisonSnapshot:
        snapshot = await service.current_or_refresh()
        if snapshot is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                {
                    "code": "COMPANY_COMPARISON_SNAPSHOT_NOT_FOUND",
                    "message": "발행된 기업 비교 스냅샷이 없습니다. 새로고침으로 생성해 주세요.",
                    "retryable": True,
                },
            )
        return snapshot

    @router.post(
        "/snapshot/refresh",
        response_model=CompanyComparisonSnapshot,
        responses=error_responses,
    )
    async def refresh_company_comparison_snapshot() -> CompanyComparisonSnapshot:
        try:
            return await service.refresh()
        except ComparisonDataError as error:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {
                    "code": error.code.upper(),
                    "message": str(error),
                    "retryable": False,
                },
            ) from error

    return router


__all__ = ["create_company_comparison_router"]
