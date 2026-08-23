"""Canonical public error response contract."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ApiErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    retryable: bool = False
    context: dict[str, Any] = Field(default_factory=dict)


class ApiErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detail: ApiErrorDetail


__all__ = ["ApiErrorDetail", "ApiErrorEnvelope"]
