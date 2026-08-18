import os
from pathlib import Path
import dotenv

PROJECT_DIR = Path(__file__).resolve().parents[2]
dotenv.load_dotenv(PROJECT_DIR / ".env")
dotenv.load_dotenv()
PROCESSED_DATA_DIR = PROJECT_DIR / "data" / "processed"
SPREADSHEET_ARTIFACT_DIR = PROJECT_DIR / "data" / "artifacts" / "spreadsheets"
EMBEDDING_ARTIFACT_DIR = PROJECT_DIR / "data" / "artifacts" / "embeddings"
VECTOR_INDEX_DIR = PROJECT_DIR / "data" / "vector_db"
DIST_DIR = PROJECT_DIR / "dist"
WORKFLOW_DIR = PROJECT_DIR / "data" / "workflows"
RUN_DIR = PROJECT_DIR / "data" / "runs"
CACHE_DIR = PROJECT_DIR / "data" / "cache"

# PostgreSQL + pgvector Configuration
PGVECTOR_URL = os.getenv(
    "PGVECTOR_URL",
    os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/rag_flow"),
)
USE_PGVECTOR = os.getenv("USE_PGVECTOR", "true").lower() in ("true", "1", "yes")

SIMILARITY_THRESHOLD = 0.95
DEV_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)

