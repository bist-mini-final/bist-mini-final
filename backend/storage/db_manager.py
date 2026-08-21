"""Database Manager for full ERD persistence in PostgreSQL.

Documented ERD Schema:
- source_files:
    - file_id (VARCHAR(64), PK): Unique identifier or content hash
    - file_name (VARCHAR(255), NOT NULL): Original name of the source file
    - file_hash (VARCHAR(64), NOT NULL): Content SHA-256 hash
    - file_type (VARCHAR(32), NOT NULL): File extension/format (e.g., excel, parquet, json)
    - file_size (BIGINT, NOT NULL): Size in bytes
    - storage_path (VARCHAR(512), NOT NULL): Path to stored file
    - created_at (TIMESTAMPTZ, DEFAULT NOW()): Record creation timestamp
- sheets:
    - sheet_id (VARCHAR(128), PK): Composite identifier ({file_id}:{sheet_name})
    - file_id (VARCHAR(64), FK -> source_files.file_id): Parent file ID
    - sheet_name (VARCHAR(128), NOT NULL): Sheet name
    - sheet_index (INT, NOT NULL): Index order of the sheet
    - is_visible (BOOLEAN, DEFAULT TRUE): Sheet visibility flag
    - row_count (INT, DEFAULT 0): Total rows in sheet
    - column_count (INT, DEFAULT 0): Total columns in sheet
    - detected_tables (JSONB, DEFAULT '[]'): Detected table boundary metadata
    - parsed_at (TIMESTAMPTZ, DEFAULT NOW()): Parsing timestamp
- langchain_pg_collection:
    - uuid (UUID, PK): Unique identifier for pgvector collection
    - name (VARCHAR, UNIQUE NOT NULL): Collection/Index name
    - cmetadata (JSON): Collection metadata
- langchain_pg_embedding:
    - id (VARCHAR, PK): Chunk embedding ID (UUID or scoped composite ID)
    - collection_id (UUID, FK -> langchain_pg_collection.uuid): Parent collection
    - embedding (vector): Dynamic embedding vector representation (HNSW indexable)
    - document (VARCHAR): Document chunk text content
    - cmetadata (JSONB): Chunk metadata (cell coordinates, headers, etc.)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import psycopg2.extras

from ..core.settings import PGVECTOR_URL
from .connection_pool import get_connection, get_pooled_raw_connection

logger = logging.getLogger(__name__)

DDL_INIT = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS source_files (
    file_id VARCHAR(64) PRIMARY KEY,
    file_name VARCHAR(255) NOT NULL,
    file_hash VARCHAR(64) NOT NULL,
    file_type VARCHAR(32) NOT NULL,
    file_size BIGINT NOT NULL,
    storage_path VARCHAR(512) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sheets (
    sheet_id VARCHAR(128) PRIMARY KEY,
    file_id VARCHAR(64) REFERENCES source_files(file_id) ON DELETE CASCADE,
    sheet_name VARCHAR(128) NOT NULL,
    sheet_index INT NOT NULL,
    is_visible BOOLEAN DEFAULT TRUE,
    row_count INT NOT NULL DEFAULT 0,
    column_count INT NOT NULL DEFAULT 0,
    detected_tables JSONB DEFAULT '[]',
    parsed_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS langchain_pg_collection (
    uuid UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR NOT NULL UNIQUE,
    cmetadata JSON
);

CREATE TABLE IF NOT EXISTS langchain_pg_embedding (
    id VARCHAR PRIMARY KEY,
    collection_id UUID REFERENCES langchain_pg_collection(uuid) ON DELETE CASCADE,
    embedding vector,
    document VARCHAR,
    cmetadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_source_files_hash ON source_files(file_hash);
CREATE INDEX IF NOT EXISTS idx_sheets_file_id ON sheets(file_id);
CREATE INDEX IF NOT EXISTS idx_langchain_cmetadata_gin ON langchain_pg_embedding USING gin (cmetadata jsonb_path_ops);
"""


class DatabaseManager:
    """PostgreSQL full ERD database manager."""

    def __init__(
        self,
        database_url: str = PGVECTOR_URL,
        *,
        ensure_schema: bool = True,
    ) -> None:
        self.database_url = database_url

    def _raw_connection(self) -> Any:
        raw_url = getattr(self, "database_url", PGVECTOR_URL).replace("postgresql+psycopg://", "postgresql://")
        return get_pooled_raw_connection(raw_url)

    def is_connected(self) -> bool:
        """Check whether a connection to the database can be established and used.
        
        Returns:
        	bool: `True` if the database connection succeeds, `False` otherwise.
        """
        try:
            conn = self._raw_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1;")
                return True
            finally:
                conn.close()
        except Exception:
            return False

    def ensure_schema(self) -> bool:
        """Create required database tables according to DDL_INIT.

        Returns:
            bool: True if schema initialization succeeded, False otherwise.
        """
        conn = None
        try:
            conn = self._raw_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(DDL_INIT)
                conn.commit()
                return True
            finally:
                conn.close()
        except Exception as err:
            logger.warning("PostgreSQL 스키마 초기화에 실패했습니다: %s", err, exc_info=True)
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
            return False

    def run_migrations(self) -> bool:
        """Run destructive or legacy schema migrations (e.g. dropping obsolete columns).

        Returns:
            bool: True if migrations succeeded, False otherwise.
        """
        conn = None
        try:
            conn = self._raw_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute("ALTER TABLE source_files DROP COLUMN IF EXISTS file_content;")
                    cur.execute("ALTER TABLE source_files DROP COLUMN IF EXISTS metadata;")
                conn.commit()
                return True
            finally:
                conn.close()
        except Exception as err:
            logger.warning("PostgreSQL 마이그레이션 실행에 실패했습니다: %s", err, exc_info=True)
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
            return False

    def save_source_file(
        self,
        file_id: str,
        file_name: str,
        file_hash: str,
        file_type: str,
        file_size: int,
        storage_path: str,
        **_ignored: Any,
    ) -> None:
        """
        Insert a source file record or update the existing record with the same file ID.
        
        Parameters:
            file_id (str): Unique identifier for the source file.
            file_name (str): Name of the source file.
            file_hash (str): Content hash of the source file.
            file_type (str): Type of the source file.
            file_size (int): Size of the source file.
            storage_path (str): Path where the source file is stored.
        """
        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO source_files (file_id, file_name, file_hash, file_type, file_size, storage_path, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (file_id) DO UPDATE SET
                        file_name = EXCLUDED.file_name,
                        file_hash = EXCLUDED.file_hash,
                        file_type = EXCLUDED.file_type,
                        file_size = EXCLUDED.file_size,
                        storage_path = EXCLUDED.storage_path;
                    """,
                    (
                        file_id,
                        file_name,
                        file_hash,
                        file_type,
                        file_size,
                        storage_path,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def delete_source_file(self, file_id_hash_or_name: str) -> bool:
        """Delete a source file by ID, hash, or filename with cascading sheets."""
        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM source_files
                    WHERE file_id = %s OR file_hash = %s;
                    """,
                    (file_id_hash_or_name, file_id_hash_or_name),
                )
                deleted = cur.rowcount > 0
                if not deleted:
                    safe_file_name = Path(file_id_hash_or_name).name
                    cur.execute(
                        """
                        SELECT file_id
                        FROM source_files
                        WHERE file_name = %s
                        ORDER BY created_at DESC
                        LIMIT 2;
                        """,
                        (safe_file_name,),
                    )
                    matches = cur.fetchmany(2)
                    if len(matches) > 1:
                        raise ValueError(
                            "동일한 파일명의 source_files 레코드가 여러 개입니다. "
                            "file_id 또는 file_hash로 삭제하세요"
                        )
                    if matches:
                        cur.execute(
                            "DELETE FROM source_files WHERE file_id = %s;",
                            (matches[0][0],),
                        )
                        deleted = cur.rowcount > 0
            conn.commit()
            return deleted
        finally:
            conn.close()

    def save_sheets(self, file_id: str, sheets_info: List[Dict[str, Any]]) -> None:
        """Insert or replace sheet records for a source file."""
        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                for s in sheets_info:
                    sheet_name = s.get("sheet_name", "Sheet1")
                    sheet_id = f"{file_id}:{sheet_name}"
                    cur.execute(
                        """
                        INSERT INTO sheets (sheet_id, file_id, sheet_name, sheet_index, is_visible, row_count, column_count, detected_tables, parsed_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (sheet_id) DO UPDATE SET
                            sheet_index = EXCLUDED.sheet_index,
                            is_visible = EXCLUDED.is_visible,
                            row_count = EXCLUDED.row_count,
                            column_count = EXCLUDED.column_count,
                            detected_tables = EXCLUDED.detected_tables,
                            parsed_at = NOW();
                        """,
                        (
                            sheet_id,
                            file_id,
                            sheet_name,
                            s.get("sheet_index", 0),
                            s.get("is_visible", True),
                            s.get("row_count", 0),
                            s.get("column_count", 0),
                            psycopg2.extras.Json(s.get("detected_tables", [])),
                        ),
                    )
            conn.commit()
        finally:
            conn.close()


def main() -> None:
    """CLI entrypoint for initializing database schema or running migrations."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Database schema management and migrations.")
    parser.add_argument("--init", action="store_true", help="Initialize ERD database tables.")
    parser.add_argument("--migrate", action="store_true", help="Run destructive/legacy database migrations.")
    args = parser.parse_args()

    manager = DatabaseManager()
    exit_code = 0

    if args.init or not args.migrate:
        print("Ensuring database schema...")
        if manager.ensure_schema():
            print("Schema initialized.")
        else:
            print("Schema initialization failed.", file=sys.stderr)
            exit_code = 1

    if args.migrate:
        print("Running database migrations...")
        if manager.run_migrations():
            print("Migrations complete.")
        else:
            print("Migrations failed.", file=sys.stderr)
            exit_code = 1

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
