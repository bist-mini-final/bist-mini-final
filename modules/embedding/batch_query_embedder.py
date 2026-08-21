from __future__ import annotations

"""Alias module forwarding to the unified EmbedderModule in embedder.py."""

from modules.embedding.embedder import (
    BatchQueryEmbedderConfigDTO,
    BatchQueryEmbedderExecutionDTO,
    BatchQueryEmbedderInputDTO,
    BatchQueryEmbedderModule,
    EmbedderConfigDTO,
    EmbedderExecutionDTO,
    EmbedderInputDTO,
    EmbedderModule,
    EmbeddingsDTO,
)

__all__ = [
    "BatchQueryEmbedderConfigDTO",
    "BatchQueryEmbedderExecutionDTO",
    "BatchQueryEmbedderInputDTO",
    "BatchQueryEmbedderModule",
    "EmbedderConfigDTO",
    "EmbedderExecutionDTO",
    "EmbedderInputDTO",
    "EmbedderModule",
    "EmbeddingsDTO",
]
