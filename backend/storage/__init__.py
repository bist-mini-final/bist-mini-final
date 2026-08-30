"""Legacy storage adapters with cycle-safe compatibility exports."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from backend.storage.db_manager import DatabaseManager
    from backend.storage.embedding_artifacts import EmbeddingArtifactStore
    from backend.storage.pgvector_store import PgVectorStore

_EXPORT_MODULES = {
    "DatabaseManager": "backend.storage.db_manager",
    "EmbeddingArtifactStore": "backend.storage.embedding_artifacts",
    "PgVectorStore": "backend.storage.pgvector_store",
}


def __getattr__(name: str) -> Any:
    """Load compatibility exports only when a caller explicitly requests one."""

    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value

__all__ = [
    "DatabaseManager",
    "EmbeddingArtifactStore",
    "PgVectorStore",
]
