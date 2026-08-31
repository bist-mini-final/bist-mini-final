"""Centralized configuration constants, model dimensions, and pricing rates across all modules."""

from __future__ import annotations

from typing import Literal

# ==============================================================================
# 1. Embedding Models & Dimensionality
# ==============================================================================
DEFAULT_EMBEDDING_MODEL: str = "text-embedding-3-small"
DEFAULT_EMBEDDING_DIMENSION: int = 1536
DEFAULT_CELL_EMBEDDING_BATCH_SIZE: int = 2048
DEFAULT_QUERY_EMBEDDING_BATCH_SIZE: int = 128

DEFAULT_EXCHANGE_RATE_KRW_PER_USD: float = 1400.0


# ==============================================================================
# 2. LLM, VLM & Reasoning Models & Pricing
# ==============================================================================
DEFAULT_LLM_MODEL: str = "gpt-5.6-luna"
DEFAULT_VLM_MODEL: str = DEFAULT_LLM_MODEL
DEFAULT_READER_MODEL: str = DEFAULT_LLM_MODEL
DEFAULT_REFINER_MODEL: str = DEFAULT_LLM_MODEL
DEFAULT_ENTITY_EXTRACTOR_MODEL: str = DEFAULT_LLM_MODEL

# ==============================================================================
# 3. Retrieval & RRF Fusion Defaults
# ==============================================================================
DEFAULT_RETRIEVAL_TOP_K: int = 100
DEFAULT_RRF_K: int = 60


# ==============================================================================
# 4. Context Expansion Defaults (PostgreSQL DB On-Demand)
# ==============================================================================
DEFAULT_PG_CONTEXT_TOP_K: int = 100
DEFAULT_PG_ADJACENT_RADIUS: int = 0
DEFAULT_PG_MAX_BLOCKS: int = 1000
DEFAULT_CONTEXT_TOP_K: int = DEFAULT_PG_CONTEXT_TOP_K
DEFAULT_CONTEXT_ADJACENT_RADIUS: int = DEFAULT_PG_ADJACENT_RADIUS
DEFAULT_CONTEXT_MAX_BLOCKS: int = DEFAULT_PG_MAX_BLOCKS


# ==============================================================================
# 5. Answer Refiner Defaults
# ==============================================================================
DEFAULT_REFINER_MODE: str = "direct_cell"
DEFAULT_REFINER_TOP_K: int = 20
DEFAULT_MAX_DIRECT_CELLS: int = 25


# ==============================================================================
# 7. Spreadsheet Structure Detection & Ingestion Defaults
# ==============================================================================
DEFAULT_STRUCTURE_MAX_ROWS: int = 400
DEFAULT_STRUCTURE_MAX_COLUMNS: int = 60
DEFAULT_HEADER_SCAN_ROWS: int = 10
DEFAULT_BOLD_RATIO_THRESHOLD: float = 0.3
DEFAULT_FILL_RATIO_THRESHOLD: float = 0.4
DEFAULT_STRUCTURE_MAX_OUTPUT_TOKENS: int = 6000
DEFAULT_STRUCTURE_MAX_CONTEXT_CELLS: int = 50000
DEFAULT_VLM_TIMEOUT_SECONDS: int = 240
DEFAULT_VLM_REASONING_EFFORT: Literal["none", "low", "medium", "high"] = "low"
DEFAULT_BFS_MERGE_GAP: int = 2
DEFAULT_BFS_MIN_NON_EMPTY_CELLS: int = 2
DEFAULT_BFS_MIN_TABLE_COLUMNS: int = 2
DEFAULT_BFS_LLM_BATCH_SIZE: int = 8
DEFAULT_SERIALIZER_VARIANT_MODE: Literal["header_only", "header_with_value", "both"] = "both"
