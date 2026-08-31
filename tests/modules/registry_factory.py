"""Explicit test composition for the production module registry."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from backend.bootstrap.module_registry import ModuleRegistry
from backend.domains.data_sources.infrastructure.filesystem.embedding_artifacts import (
    EmbeddingArtifactStore,
)
from backend.domains.data_sources.infrastructure.pgvector import PgVectorStore
from backend.domains.data_sources.infrastructure.postgres import PostgresSourceFileRepository


def create_test_registry(
    *,
    source_files: Any | None = None,
    artifact_dir: Path | None = None,
) -> ModuleRegistry:
    repository = source_files or PostgresSourceFileRepository()
    return ModuleRegistry(
        completion_client=MagicMock(),
        embedding_encoder=MagicMock(),
        embedding_artifact_store=EmbeddingArtifactStore(
            artifact_dir
        ) if artifact_dir is not None else EmbeddingArtifactStore(),
        pgvector_store=PgVectorStore(),
        source_files=repository,
    )


__all__ = ["create_test_registry"]
