import os
from pathlib import Path

import dotenv

PROJECT_DIR = Path(__file__).resolve().parents[2]
dotenv.load_dotenv(PROJECT_DIR / ".env")
PROCESSED_DATA_DIR = PROJECT_DIR / "data" / "source_files"
SOURCE_FILES_DIR = PROCESSED_DATA_DIR
SPREADSHEET_ARTIFACT_DIR = PROJECT_DIR / "data" / "artifacts" / "spreadsheets"
EMBEDDING_ARTIFACT_DIR = PROJECT_DIR / "data" / "artifacts" / "embeddings"
VECTOR_INDEX_DIR = PROJECT_DIR / "data" / "vector_db"
DIST_DIR = PROJECT_DIR / "dist"
WORKFLOW_DIR = PROJECT_DIR / "data" / "workflows"
RUN_DIR = PROJECT_DIR / "data" / "runs"
CACHE_DIR = PROJECT_DIR / "data" / "cache"
BENCHMARK_DIR = PROJECT_DIR / "data" / "benchmarks"


def _positive_int_environment(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if value < 1:
        raise ValueError(f"{name} must be at least 1")
    return value


PLAYGROUND_MAX_CONCURRENCY = _positive_int_environment(
    "PLAYGROUND_MAX_CONCURRENCY",
    4,
)
KUBERNETES_INGESTION_QUEUE = os.getenv(
    "KUBERNETES_INGESTION_QUEUE",
    "excel-ingestion",
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
