from fastapi import APIRouter, HTTPException
from starlette import status

from backend.contracts import ApiErrorEnvelope

from .calculator import ComparisonDataError
from .models import CompanyComparisonRequest, CompanyComparisonResponse, FinancialLeagueResponse
from .service import CompanyComparisonService


def create_company_comparison_router(
    service: CompanyComparisonService,
) -> APIRouter:
    router = APIRouter(prefix="/bi/comparisons", tags=["BI Comparison"])

    @router.get("/league", response_model=FinancialLeagueResponse)
    def get_financial_league() -> FinancialLeagueResponse:
        try:
            return service.league()
        except ComparisonDataError as error:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {
                    "code": error.code.upper(),
                    "message": str(error),
                    "retryable": False,
                },
            ) from error

    @router.post(
        "/analyze",
        response_model=CompanyComparisonResponse,
        responses={
            404: {"model": ApiErrorEnvelope},
            409: {"model": ApiErrorEnvelope},
            422: {"model": ApiErrorEnvelope},
            500: {"model": ApiErrorEnvelope},
            503: {"model": ApiErrorEnvelope},
        },
    )
    def analyze_company_comparison(
        request: CompanyComparisonRequest,
    ) -> CompanyComparisonResponse:
        try:
            return service.analyze(request)
        except ComparisonDataError as error:
            not_found = error.code == "comparison_company_not_found"
            raise HTTPException(
                status.HTTP_404_NOT_FOUND if not_found else status.HTTP_409_CONFLICT,
                {
                    "code": error.code.upper(),
                    "message": str(error),
                    "retryable": False,
                },
            ) from error

    return router


__all__ = ["create_company_comparison_router"]
