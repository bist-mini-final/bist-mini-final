"""Source-file and worksheet persistence capability."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import psycopg2.extras

from backend.platform.postgres.pool import get_pooled_async_connection

from .base import DatabaseConnectionCapability


class SourceFileRepositoryMixin(DatabaseConnectionCapability):
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
                    INSERT INTO source_files (file_id, file_name, file_hash, file_type, file_size, storage_path, is_deleted, deleted_at, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, FALSE, NULL, NOW())
                    ON CONFLICT (file_id) DO UPDATE SET
                        file_name = EXCLUDED.file_name,
                        file_hash = EXCLUDED.file_hash,
                        file_type = EXCLUDED.file_type,
                        file_size = EXCLUDED.file_size,
                        storage_path = EXCLUDED.storage_path,
                        is_deleted = FALSE,
                        deleted_at = NULL;
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

    async def save_source_file_async(
        self,
        file_id: str,
        file_name: str,
        file_hash: str,
        file_type: str,
        file_size: int,
        storage_path: str,
        **_ignored: Any,
    ) -> None:
        """Persist upload metadata through native async PostgreSQL I/O."""
        async with get_pooled_async_connection(self.database_url) as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    INSERT INTO source_files (file_id, file_name, file_hash, file_type, file_size, storage_path, is_deleted, deleted_at, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, FALSE, NULL, NOW())
                    ON CONFLICT (file_id) DO UPDATE SET
                        file_name = EXCLUDED.file_name,
                        file_hash = EXCLUDED.file_hash,
                        file_type = EXCLUDED.file_type,
                        file_size = EXCLUDED.file_size,
                        storage_path = EXCLUDED.storage_path,
                        is_deleted = FALSE,
                        deleted_at = NULL;
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
            await connection.commit()

    def delete_source_file(
        self,
        file_id_hash_or_name: str,
        *,
        actor_id: str = "system",
        request_id: str | None = None,
    ) -> bool:
        """Soft-delete source metadata by ID, hash, or unambiguous filename."""
        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                self._set_audit_context(cur, actor_id=actor_id, request_id=request_id)
                cur.execute(
                    """
                    UPDATE source_files
                    SET is_deleted = TRUE, deleted_at = NOW()
                    WHERE (file_id = %s OR file_hash = %s) AND is_deleted = FALSE;
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
                        WHERE file_name = %s AND is_deleted = FALSE
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
                            "UPDATE source_files SET is_deleted = TRUE, "
                            "deleted_at = NOW() WHERE file_id = %s "
                            "AND is_deleted = FALSE;",
                            (matches[0][0],),
                        )
                        deleted = cur.rowcount > 0
            conn.commit()
            return deleted
        finally:
            conn.close()

    @staticmethod
    def _set_audit_context(
        cursor: Any,
        *,
        actor_id: str,
        request_id: str | None,
    ) -> None:
        cursor.execute(
            "SELECT set_config('app.audit_actor_id', %s, TRUE), "
            "set_config('app.audit_request_id', %s, TRUE)",
            (actor_id[:128], (request_id or "")[:128]),
        )

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

    def list_sheets(self, file_id: str) -> List[Dict[str, Any]]:
        """Return normalized sheet metadata for one workbook in display order."""

        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT sheet_name, sheet_index, is_visible, row_count,
                           column_count, detected_tables, parsed_at
                    FROM sheets
                    WHERE file_id = %s
                    ORDER BY sheet_index, sheet_name;
                    """,
                    (file_id,),
                )
                return [
                    {
                        "sheet_name": str(row[0]),
                        "sheet_index": int(row[1]),
                        "is_visible": bool(row[2]),
                        "row_count": int(row[3]),
                        "column_count": int(row[4]),
                        "detected_tables": row[5] or [],
                        "parsed_at": (
                            row[6].isoformat() if hasattr(row[6], "isoformat") else str(row[6])
                        ),
                    }
                    for row in cur.fetchall()
                ]
        finally:
            conn.close()


__all__ = ["SourceFileRepositoryMixin"]
