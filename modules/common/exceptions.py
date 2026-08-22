"""Standardized pipeline domain exception hierarchy for modular RAG execution."""

from __future__ import annotations

from typing import Any, Dict, Optional


class PipelineBaseError(Exception):
    """Root exception for all pipeline module, workflow, and engine failures."""

    def __init__(
        self,
        message: str,
        *,
        module_type: Optional[str] = None,
        error_code: str = "PIPELINE_ERROR",
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.module_type = module_type
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_code": self.error_code,
            "message": self.message,
            "module_type": self.module_type,
            "details": self.details,
        }

    def __str__(self) -> str:
        prefix = f"[{self.module_type}] " if self.module_type else ""
        return f"{prefix}{self.message}"


class ModuleExecutionError(PipelineBaseError):
    """Raised when a pipeline module fails during execution (backward compatible)."""

    def __init__(
        self,
        message: str,
        *,
        module_type: Optional[str] = None,
        error_code: str = "MODULE_EXECUTION_ERROR",
        status_code: int = 422,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message,
            module_type=module_type,
            error_code=error_code,
            status_code=status_code,
            details=details,
        )


class ModuleValidationError(ModuleExecutionError):
    """Input or configuration validation failed for a module."""

    def __init__(
        self,
        message: str = "모듈 입력 또는 설정 검증에 실패했습니다.",
        *,
        module_type: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message,
            module_type=module_type,
            error_code="MODULE_VALIDATION_ERROR",
            status_code=422,
            details=details,
        )


class ProviderApiError(ModuleExecutionError):
    """External AI provider API error (LLM, Embedding API, rate limits, timeouts)."""

    def __init__(
        self,
        message: str,
        *,
        module_type: Optional[str] = None,
        provider: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        full_details = {"provider": provider, **(details or {})}
        super().__init__(
            message,
            module_type=module_type,
            error_code="PROVIDER_API_ERROR",
            status_code=502,
            details=full_details,
        )


class StorageError(ModuleExecutionError):
    """Database, pgvector, artifact, or filesystem storage error."""

    def __init__(
        self,
        message: str,
        *,
        module_type: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message,
            module_type=module_type,
            error_code="STORAGE_ERROR",
            status_code=500,
            details=details,
        )


class DocumentParsingError(ModuleExecutionError):
    """Excel, spreadsheet, or visual structure parsing error."""

    def __init__(
        self,
        message: str,
        *,
        module_type: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message,
            module_type=module_type,
            error_code="DOCUMENT_PARSING_ERROR",
            status_code=422,
            details=details,
        )


__all__ = [
    "DocumentParsingError",
    "ModuleExecutionError",
    "ModuleValidationError",
    "PipelineBaseError",
    "ProviderApiError",
    "StorageError",
]
