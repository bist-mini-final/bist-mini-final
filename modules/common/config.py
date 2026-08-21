"""Centralized configuration constants and default model options across modules."""

from __future__ import annotations

from typing import List

# ==============================================================================
# Embedding Configuration (Canonical standard: text-embedding-3-large / 3072D)
# ==============================================================================
DEFAULT_EMBEDDING_MODEL: str = "text-embedding-3-large"
DEFAULT_EMBEDDING_DIMENSION: int = 3072
EMBEDDING_MODEL_OPTIONS: List[str] = [
    "text-embedding-3-large",
]

# ==============================================================================
# LLM & Reasoning Models
# ==============================================================================
DEFAULT_LLM_MODEL: str = "gpt-5.6-luna"
LLM_MODEL_OPTIONS: List[str] = [
    "gpt-5.6-luna"
]

# Vision Language Model (for Excel sheet structure detection)
DEFAULT_VLM_MODEL: str = "gpt-5.6-luna"

# ==============================================================================
# Retrieval & RAG Defaults
# ==============================================================================
DEFAULT_RETRIEVAL_TOP_K: int = 100
DEFAULT_RRF_K: int = 60
DEFAULT_CONTEXT_WINDOW: int = 3
