"""Centralized configuration constants and default model options across all modules."""

from __future__ import annotations

from typing import List

# ==============================================================================
# 1. Embedding Models (Canonical standard: text-embedding-3-large / 3072D)
# ==============================================================================
DEFAULT_EMBEDDING_MODEL: str = "text-embedding-3-large"
DEFAULT_EMBEDDING_DIMENSION: int = 3072
EMBEDDING_MODEL_OPTIONS: List[str] = [
    "text-embedding-3-large",
]
DEFAULT_CELL_EMBEDDING_BATCH_SIZE: int = 2048


# ==============================================================================
# 2. LLM, VLM & Reasoning Models
# ==============================================================================
DEFAULT_LLM_MODEL: str = "gpt-5.6-luna"
LLM_MODEL_OPTIONS: List[str] = [
    "gpt-5.6-luna",
]
DEFAULT_VLM_MODEL: str = "gpt-5.6-luna"
DEFAULT_ROUTER_MODEL: str = "gpt-5.6-luna"
DEFAULT_READER_MODEL: str = "gpt-5.6-luna"
DEFAULT_REFINER_MODEL: str = "gpt-5.6-luna"


# ==============================================================================
# 3. Query Decomposition, Semantic Routing & Matching Defaults
# ==============================================================================
DEFAULT_QUERY_INPUT_THRESHOLD: float = 0.95
DEFAULT_SEMANTIC_THRESHOLD: float = 0.74
DEFAULT_SEMANTIC_TOP_K: int = 5
DEFAULT_SEMANTIC_VOTE_MARGIN: float = 0.05
DEFAULT_PLAN_REUSE_THRESHOLD: float = 0.80


# ==============================================================================
# 4. Retrieval, RRF Fusion & Context Expansion Defaults
# ==============================================================================
DEFAULT_RETRIEVAL_TOP_K: int = 100
DEFAULT_RRF_K: int = 60
DEFAULT_ADJACENT_RADIUS: int = 3
DEFAULT_CONTEXT_WINDOW: int = DEFAULT_ADJACENT_RADIUS  # Backwards compatibility alias
DEFAULT_MAX_BLOCKS: int = 500
DEFAULT_MIN_SCOPE_CONFIDENCE: float = 0.80


# ==============================================================================
# 5. Answer Refiner Defaults
# ==============================================================================
DEFAULT_REFINER_MODE: str = "direct_cell"
DEFAULT_REFINER_TOP_K: int = 20


# ==============================================================================
# 6. Spreadsheet Structure Detection & Ingestion Defaults
# ==============================================================================
DEFAULT_STRUCTURE_MAX_ROWS: int = 400
DEFAULT_STRUCTURE_MAX_COLUMNS: int = 60
DEFAULT_HEADER_SCAN_ROWS: int = 10
DEFAULT_BOLD_RATIO_THRESHOLD: float = 0.3
DEFAULT_FILL_RATIO_THRESHOLD: float = 0.4
DEFAULT_STRUCTURE_MAX_OUTPUT_TOKENS: int = 6000
DEFAULT_VLM_TIMEOUT_SECONDS: int = 240
DEFAULT_BFS_MERGE_GAP: int = 2
DEFAULT_BFS_MIN_NON_EMPTY_CELLS: int = 2
DEFAULT_BFS_MIN_TABLE_COLUMNS: int = 2
DEFAULT_BFS_LLM_BATCH_SIZE: int = 8
