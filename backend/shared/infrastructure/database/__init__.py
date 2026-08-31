"""Compatibility imports for :mod:`backend.platform.postgres.repositories`."""

from backend.platform.postgres.repositories import (
    AsyncPostgresRepository,
    DatabaseUrlProvider,
    SyncPostgresRepository,
)

__all__ = [
    "AsyncPostgresRepository",
    "DatabaseUrlProvider",
    "SyncPostgresRepository",
]
