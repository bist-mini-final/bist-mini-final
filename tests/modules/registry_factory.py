"""Explicit test composition for the production module registry."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from backend.engine.runtime.registry import ModuleRegistry
from backend.storage.db_manager import DatabaseManager
from backend.storage.embedding_artifacts import EmbeddingArtifactStore
from backend.storage.pgvector_store import PgVectorStore


def create_test_registry(
    *,
    db_manager: Any | None = None,
    artifact_dir: Path | None = None,
) -> ModuleRegistry:
    database = db_manager or DatabaseManager()
    return ModuleRegistry(
        completion_client=MagicMock(),
        embedding_encoder=MagicMock(),
        embedding_artifact_store=EmbeddingArtifactStore(
            artifact_dir
        ) if artifact_dir is not None else EmbeddingArtifactStore(),
        pgvector_store=PgVectorStore(),
        db_manager=database,
    )


__all__ = ["create_test_registry"]
