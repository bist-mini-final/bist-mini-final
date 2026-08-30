"""Central FastAPI exception-to-contract mapping."""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from backend.api.error_mapping import error_envelope, http_error_envelope
from backend.shared.domain import (
    ApplicationConflict,
    ApplicationError,
    ApplicationInternalError,
    ApplicationValidationError,
    PayloadTooLargeError,
    ResourceNotFoundError,
    RetryableInfrastructureError,
)
from modules.common.exceptions import PipelineBaseError

logger = logging.getLogger("backend.api.exceptions")


def register_global_exception_handlers(application: FastAPI) -> None:
    """Map framework, domain, validation, and unknown failures consistently."""

    @application.exception_handler(PipelineBaseError)
    async def pipeline_exception_handler(
        request: Request,
        exc: PipelineBaseError,
    ) -> JSONResponse:
        del request
        payload = exc.to_dict()
        return JSONResponse(
            status_code=exc.status_code,
            content=error_envelope(
                code=str(payload["error_code"]),
                message=str(payload["message"]),
                retryable=exc.status_code >= 500,
                context={
                    "module_type": payload.get("module_type"),
                    **(payload.get("details") or {}),
                },
            ),
        )

    @application.exception_handler(ValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: ValidationError,
    ) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=422,
            content=error_envelope(
                code="VALIDATION_ERROR",
                message="데이터 유효성 검증에 실패했습니다.",
                context={"errors": exc.errors(include_url=False)},
            ),
        )

    @application.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request,
        exc: HTTPException,
    ) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=exc.status_code,
            content=http_error_envelope(exc.detail, exc.status_code),
            headers=exc.headers,
        )

    @application.exception_handler(ApplicationError)
    async def application_exception_handler(
        request: Request,
        exc: ApplicationError,
    ) -> JSONResponse:
        del request
        if isinstance(exc, PayloadTooLargeError):
            status_code = 413
        elif isinstance(exc, ResourceNotFoundError):
            status_code = 404
        elif isinstance(exc, ApplicationConflict):
            status_code = 409
        elif isinstance(exc, ApplicationValidationError):
            status_code = 422
        elif isinstance(exc, RetryableInfrastructureError):
            status_code = 503
        elif isinstance(exc, ApplicationInternalError):
            status_code = 500
        else:
            status_code = 500
        return JSONResponse(
            status_code=status_code,
            content=error_envelope(
                code=exc.code,
                message=exc.message,
                retryable=exc.retryable,
                context=exc.context,
            ),
        )

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        logger.error(
            "Unhandled server exception for %s %s: %s",
            request.method,
            request.url.path,
            exc,
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content=error_envelope(
                code="INTERNAL_SERVER_ERROR",
                message="서버 내부 오류가 발생했습니다.",
                retryable=True,
            ),
        )


__all__ = ["register_global_exception_handlers"]
