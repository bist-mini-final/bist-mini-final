"""Company-comparison domain errors."""

from __future__ import annotations


class ComparisonDataError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ComparisonSnapshotIntegrityError(RuntimeError):
    """Raised when a stored envelope and its domain payload disagree."""


__all__ = ["ComparisonDataError", "ComparisonSnapshotIntegrityError"]

