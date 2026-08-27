from fastapi import APIRouter, HTTPException, Response
from starlette import status

from backend.contracts import ApiErrorEnvelope

from .calculator import ComparisonDataError
from .models import CompanyComparisonRequest, CompanyComparisonResponse, FinancialLeagueResponse
from .service import CompanyComparisonService


def create_company_comparison_router(
    service: CompanyComparisonService,
    *,
    prefix: str = "/company-comparisons",
    include_in_schema: bool = True,
    legacy_alias: bool = False,
) -> APIRouter:
    router = APIRouter(
        prefix=prefix,
        tags=["기업 비교 분석"],
        include_in_schema=include_in_schema,
    )

    def mark_deprecated(response: Response, successor_path: str) -> None:
        if not legacy_alias:
            return
        response.headers["Deprecation"] = "true"
        response.headers["Link"] = f"<{successor_path}>; rel=\"successor-version\""

    @router.get("/league", response_model=FinancialLeagueResponse)
    def get_financial_league(response: Response) -> FinancialLeagueResponse:
        mark_deprecated(response, "/api/v1/company-comparisons/league")
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
        response: Response,
    ) -> CompanyComparisonResponse:
        mark_deprecated(response, "/api/v1/company-comparisons/analyze")
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
