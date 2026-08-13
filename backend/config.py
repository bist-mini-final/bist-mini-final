from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
PROCESSED_DATA_DIR = PROJECT_DIR / "data" / "processed"
SPREADSHEET_ARTIFACT_DIR = PROJECT_DIR / "data" / "artifacts" / "spreadsheets"
EMBEDDING_ARTIFACT_DIR = PROJECT_DIR / "data" / "artifacts" / "embeddings"
VECTOR_INDEX_DIR = PROJECT_DIR / "data" / "vector_db"
DIST_DIR = PROJECT_DIR / "dist"
WORKFLOW_DIR = PROJECT_DIR / "data" / "workflows"
RUN_DIR = PROJECT_DIR / "data" / "runs"
CACHE_DIR = PROJECT_DIR / "data" / "cache"
BENCHMARK_DIR = PROJECT_DIR / "data" / "benchmarks"

SIMILARITY_THRESHOLD = 0.65
DEV_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)
