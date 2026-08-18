"""Database Manager for full ERD persistence in PostgreSQL (source_files, sheets, document_chunks, vector_indexes)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import psycopg2
import psycopg2.extras

from ..core.settings import PGVECTOR_URL

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
    name VARCHAR PRIMARY KEY,
    cmetadata JSON,
    uuid UUID UNIQUE DEFAULT gen_random_uuid()
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

    def __init__(self, database_url: str = PGVECTOR_URL) -> None:
        self.database_url = database_url
        self.ensure_schema()

    def _raw_connection(self) -> psycopg2.extensions.connection:
        raw_url = self.database_url.replace("postgresql+psycopg://", "postgresql://")
        return psycopg2.connect(raw_url)

    def is_connected(self) -> bool:
        try:
            conn = self._raw_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
            conn.close()
            return True
        except Exception:
            return False

    def ensure_schema(self) -> None:
        """Create all required tables if they don't exist and migrate columns."""
        try:
            conn = self._raw_connection()
            with conn.cursor() as cur:
                cur.execute(DDL_INIT)
                cur.execute("ALTER TABLE source_files DROP COLUMN IF EXISTS file_content;")
                cur.execute("ALTER TABLE source_files DROP COLUMN IF EXISTS metadata;")
            conn.commit()
            conn.close()
        except Exception:
            pass

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
        """Upsert a source file record in PostgreSQL with storage_path."""
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

    def delete_source_file(self, file_id_or_hash: str) -> bool:
        """Delete a source file and its cascading sheets from PostgreSQL."""
        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM source_files WHERE file_id = %s OR file_hash = %s;",
                    (file_id_or_hash, file_id_or_hash),
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

    def get_detected_tables(self, workbook_hash: str) -> List[Dict[str, Any]]:
        """Return all detected_tables rows from the sheets table for the given workbook hash.

        Used by the partial re-run feature to restore Step 1 (Luna VLM) results when
        re-starting the pipeline from Step 2 (Serializer).

        Returns a flat list of table dicts, each compatible with ClassifiedTableDTO(**t).
        """
        import logging
        _log = logging.getLogger(__name__)

        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT sheet_name, detected_tables FROM sheets WHERE file_id = %s ORDER BY sheet_index;",
                    (workbook_hash,),
                )
                rows = cur.fetchall()

            tables: List[Dict[str, Any]] = []
            for sheet_name, detected in rows:
                if not detected:
                    continue
                # Normalise: psycopg2 returns JSONB as Python object
                if isinstance(detected, dict):
                    # Stored as single object instead of array — wrap it
                    detected = [detected]
                if not isinstance(detected, list):
                    _log.warning(
                        "[DB] sheets.detected_tables for %s/%s has unexpected type %s — skipping",
                        workbook_hash[:16], sheet_name, type(detected).__name__,
                    )
                    continue
                for item in detected:
                    if not isinstance(item, dict):
                        _log.warning(
                            "[DB] Non-dict entry in detected_tables for %s/%s — skipping",
                            workbook_hash[:16], sheet_name,
                        )
                        continue
                    # Validate minimum required fields for ClassifiedTableDTO
                    if "sheet_name" not in item or "regions" not in item:
                        _log.warning(
                            "[DB] detected_tables entry missing sheet_name or regions for %s — skipping",
                            sheet_name,
                        )
                        continue
                    tables.append(item)

            _log.info(
                "[DB] get_detected_tables: %d tables restored for workbook %s",
                len(tables), workbook_hash[:16],
            )
            return tables
        finally:
            conn.close()

