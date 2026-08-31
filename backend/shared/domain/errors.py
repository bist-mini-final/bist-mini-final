"""Cross-domain application failure hierarchy without HTTP dependencies."""

from __future__ import annotations

from typing import Any


class ApplicationError(Exception):
    code = "APPLICATION_ERROR"
    retryable = False

    def __init__(
        self,
        message: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.context = context or {}


class ApplicationValidationError(ApplicationError):
    code = "VALIDATION_ERROR"


class ResourceNotFoundError(ApplicationError):
    code = "RESOURCE_NOT_FOUND"


class ApplicationConflict(ApplicationError):
    code = "RESOURCE_CONFLICT"


class PayloadTooLargeError(ApplicationValidationError):
    code = "PAYLOAD_TOO_LARGE"


class ApplicationInternalError(ApplicationError):
    code = "APPLICATION_INTERNAL_ERROR"
    retryable = True


class RetryableInfrastructureError(ApplicationError):
    code = "INFRASTRUCTURE_UNAVAILABLE"
    retryable = True


__all__ = [
    "ApplicationConflict",
    "ApplicationError",
    "ApplicationInternalError",
    "ApplicationValidationError",
    "PayloadTooLargeError",
    "ResourceNotFoundError",
    "RetryableInfrastructureError",
]
