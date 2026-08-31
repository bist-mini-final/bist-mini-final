"""Connection capabilities shared by composed workflow repositories."""

from __future__ import annotations

from typing import Any


class WorkflowDatabaseCapability:
    database_url: str

    def _raw_connection(self) -> Any:
        raise NotImplementedError

    def _advisory_lock_connection(self) -> Any:
        raise NotImplementedError


__all__ = ["WorkflowDatabaseCapability"]
