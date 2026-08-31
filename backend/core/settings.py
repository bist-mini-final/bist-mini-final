import os
from pathlib import Path

import dotenv

PROJECT_DIR = Path(__file__).resolve().parents[2]
dotenv.load_dotenv(PROJECT_DIR / ".env")
PROCESSED_DATA_DIR = PROJECT_DIR / "data" / "source_files"
SOURCE_FILES_DIR = PROCESSED_DATA_DIR
SPREADSHEET_ARTIFACT_DIR = PROJECT_DIR / "data" / "artifacts" / "spreadsheets"
EMBEDDING_ARTIFACT_DIR = PROJECT_DIR / "data" / "artifacts" / "embeddings"
DIST_DIR = PROJECT_DIR / "dist"
WORKFLOW_DIR = PROJECT_DIR / "data" / "workflows"
RUN_DIR = PROJECT_DIR / "data" / "runs"
CACHE_DIR = PROJECT_DIR / "data" / "cache"
CHAT_UPLOAD_DIR = PROJECT_DIR / "data" / "chat_uploads"
BENCHMARK_SET_DIR = PROJECT_DIR / "data" / "benchmark_sets"


def _positive_int_environment(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if value < 1:
        raise ValueError(f"{name} must be at least 1")
    return value


def _positive_float_environment(name: str, default: float) -> float:
    raw_value = os.getenv(name, str(default))
    try:
        value = float(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} must be a number") from error
    if value <= 0:
        raise ValueError(f"{name} must be greater than 0")
    return value


def _boolean_environment(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


KUBERNETES_WORKFLOW_QUEUE = os.getenv(
    "KUBERNETES_WORKFLOW_QUEUE",
    "workflow-core",
)
REDIS_URL = os.getenv("REDIS_URL", "").strip()
INGESTION_SHARDS_ENABLED = _boolean_environment(
    "INGESTION_SHARDS_ENABLED",
    False,
)
INGESTION_SHARD_POLL_SECONDS = _positive_float_environment(
    "INGESTION_SHARD_POLL_SECONDS",
    1.0,
)
INGESTION_SHARD_WAIT_TIMEOUT_SECONDS = _positive_int_environment(
    "INGESTION_SHARD_WAIT_TIMEOUT_SECONDS",
    21_000,
)
INGESTION_VECTOR_SHARD_SIZE = _positive_int_environment(
    "INGESTION_VECTOR_SHARD_SIZE",
    4096,
)

# PostgreSQL + pgvector Configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    os.getenv("PGVECTOR_URL", "postgresql://postgres:postgres@localhost:5432/rag_flow"),
)
PGVECTOR_URL = DATABASE_URL
USE_PGVECTOR = os.getenv("USE_PGVECTOR", "true").lower() in ("true", "1", "yes")

SIMILARITY_THRESHOLD = 0.95
DEV_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)
