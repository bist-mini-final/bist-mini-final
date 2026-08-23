"""Map internal exceptions and HTTP details to one public envelope."""

from __future__ import annotations

from typing import Any

from backend.contracts import ApiErrorDetail, ApiErrorEnvelope


def error_envelope(
    *,
    code: str,
    message: str,
    retryable: bool = False,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return ApiErrorEnvelope(
        detail=ApiErrorDetail(
            code=code,
            message=message,
            retryable=retryable,
            context=context or {},
        )
    ).model_dump(mode="json")


def http_error_envelope(detail: Any, status_code: int) -> dict[str, Any]:
    if isinstance(detail, dict):
        raw_context = detail.get("context")
        context = raw_context if isinstance(raw_context, dict) else {}
        return error_envelope(
            code=str(detail.get("code") or f"HTTP_{status_code}"),
            message=str(
                detail.get("message")
                or detail.get("detail")
                or f"HTTP 요청이 실패했습니다. ({status_code})"
            ),
            retryable=bool(detail.get("retryable", status_code >= 500)),
            context=context,
        )
    return error_envelope(
        code=f"HTTP_{status_code}",
        message=str(detail or f"HTTP 요청이 실패했습니다. ({status_code})"),
        retryable=status_code >= 500,
    )


__all__ = ["error_envelope", "http_error_envelope"]
