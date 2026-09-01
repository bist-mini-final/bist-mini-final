"""Pgvector collection catalog, health, deletion, and index maintenance."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Sequence
from urllib.parse import urlparse

from backend.core.settings import PGVECTOR_URL
from backend.platform.pgvector.errors import PgVectorStoreError
from backend.platform.postgres.pool import get_pooled_async_connection
from modules.common.config import DEFAULT_EMBEDDING_DIMENSION, DEFAULT_EMBEDDING_MODEL

from .capabilities import PgVectorConnectionCapability

logger = logging.getLogger(__name__)

VECTOR_INDEX_STRATEGY = "binary_quantized_hnsw_exact_rerank"
VECTOR_PARTITION_STRATEGY = "collection_local_partial_indexes"
_CONCURRENT_OPTIMIZED_INDEX_NAMES = (
    "idx_langchain_pg_embedding_cell_id",
    "idx_langchain_pg_embedding_cell_coord_upper",
    "idx_langchain_pg_embedding_workbook_hash",
    "idx_langchain_pg_embedding_company_name",
    "idx_langchain_pg_embedding_sheet_name",
    "idx_langchain_pg_embedding_sheet_row",
    "idx_langchain_pg_embedding_collection_id",
    "idx_langchain_pg_embedding_document_fts",
)


class PgVectorCatalogMixin(PgVectorConnectionCapability):
    """Read-side catalog and operational index maintenance capability."""

    @staticmethod
    def _json_mapping(value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        return {}

    def is_connected(self) -> bool:
        """Check if PostgreSQL + pgvector is reachable."""
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

    def get_db_info(self) -> Dict[str, Any]:
        """Return connection details, versions, and vector collection statistics."""
        raw_url = getattr(self, "database_url", PGVECTOR_URL).replace(
            "postgresql+psycopg://", "postgresql://"
        )
        parsed = urlparse(raw_url)
        safe_host = parsed.hostname or "localhost"
        port = parsed.port or 5432
        db_name = parsed.path.lstrip("/") or "rag_flow"

        try:
            conn = self._raw_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT version();")
                    pg_version = cur.fetchone()[0]

                    cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector';")
                    ext_row = cur.fetchone()
                    vector_version = ext_row[0] if ext_row else "not installed"

                    # The physical table names are retained for data compatibility.
                    cur.execute(
                        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'langchain_pg_collection';"
                    )
                    has_collections = cur.fetchone()[0] > 0

                    total_indexes = 0
                    total_chunks = 0
                    binary_quantized_indexes = 0
                    embedding_table_partitioned = False
                    if has_collections:
                        cur.execute("SELECT COUNT(*) FROM langchain_pg_collection;")
                        total_indexes = cur.fetchone()[0]
                        cur.execute("SELECT COUNT(*) FROM langchain_pg_embedding;")
                        total_chunks = cur.fetchone()[0]
                        cur.execute(
                            """
                            SELECT relkind = 'p'
                            FROM pg_catalog.pg_class
                            WHERE oid = 'langchain_pg_embedding'::regclass;
                            """
                        )
                        layout_row = cur.fetchone()
                        embedding_table_partitioned = bool(layout_row and layout_row[0])
                        cur.execute(
                            """
                            SELECT COUNT(*)
                            FROM pg_catalog.pg_indexes
                            WHERE schemaname = current_schema()
                              AND tablename = 'langchain_pg_embedding'
                              AND indexname LIKE 'idx_lc_hnsw_bq_c_%';
                            """
                        )
                        binary_quantized_indexes = int(cur.fetchone()[0])
            finally:
                conn.close()

            return {
                "connected": True,
                "host": safe_host,
                "port": port,
                "database": db_name,
                "postgres_version": pg_version.split()[1] if pg_version else "16",
                "pgvector_version": vector_version,
                "framework": "psycopg + pgvector",
                "total_indexes": total_indexes,
                "total_chunks": total_chunks,
                "vector_index_strategy": VECTOR_INDEX_STRATEGY,
                "vector_index_count": binary_quantized_indexes,
                "partition_strategy": VECTOR_PARTITION_STRATEGY,
                "embedding_table_partitioned": embedding_table_partitioned,
            }
        except Exception as err:
            return {
                "connected": False,
                "host": safe_host,
                "port": port,
                "database": db_name,
                "framework": "psycopg + pgvector",
                "error": str(err),
                "total_indexes": 0,
                "total_chunks": 0,
            }

    def list_indexes(self) -> List[Dict[str, Any]]:
        """
        List all collections registered in the pgvector storage.

        Returns:
            List[Dict[str, Any]]: Collection summaries with metadata and document counts.
        """
        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'langchain_pg_collection';"
                )
                if cur.fetchone()[0] == 0:
                    return []

                cur.execute(
                    """
                    SELECT
                        collection.name,
                        collection.cmetadata,
                        CASE
                            WHEN collection.cmetadata->>'document_count' ~ '^\\d+$'
                                THEN (collection.cmetadata->>'document_count')::bigint
                            ELSE (
                                SELECT COUNT(*)
                                FROM langchain_pg_embedding AS embedding
                                WHERE embedding.collection_id = collection.uuid
                            )
                        END AS chunk_count
                    FROM langchain_pg_collection AS collection
                    ORDER BY collection.name;
                    """
                )
                rows = cur.fetchall()
        finally:
            conn.close()

        results = []
        for r in rows:
            name = r[0]
            meta = r[1] or {}
            meta = self._json_mapping(meta)
            count = r[2]
            results.append(
                {
                    "index_id": name,
                    "file_name": meta.get("file_name", "unknown"),
                    "workbook_hash": meta.get("workbook_hash", ""),
                    "company_name": meta.get("company_name", ""),
                    "ticker": meta.get("ticker", ""),
                    "model": meta.get("model", DEFAULT_EMBEDDING_MODEL),
                    "dimension": meta.get("dimension", DEFAULT_EMBEDDING_DIMENSION),
                    "document_count": count,
                    "created_at": meta.get("created_at") or datetime.now(timezone.utc).isoformat(),
                    "storage": "PostgreSQL + pgvector",
                    "duration_seconds": meta.get("duration_seconds"),
                    "total_tokens": meta.get("total_tokens"),
                    "estimated_cost_usd": meta.get("estimated_cost_usd"),
                    "estimated_cost_krw": meta.get("estimated_cost_krw"),
                    "batch_size": meta.get("batch_size"),
                }
            )
        return results

    def list_data_scopes(self) -> List[Dict[str, Any]]:
        """Return the compact collection catalog used by query routing.

        Document counts come from collection metadata and sheet names come from
        the normalized ``sheets`` table, so routing never scans the embedding
        table merely to discover available data.
        """
        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        collection.name,
                        collection.cmetadata,
                        COALESCE(
                            ARRAY(
                                SELECT sheet.sheet_name
                                FROM sheets AS sheet
                                WHERE sheet.file_id = collection.cmetadata->>'workbook_hash'
                                  AND sheet.is_visible = TRUE
                                ORDER BY sheet.sheet_index, sheet.sheet_name
                            ),
                            ARRAY[]::text[]
                        ) AS sheet_names
                    FROM langchain_pg_collection AS collection
                    ORDER BY collection.name;
                    """
                )
                rows = cur.fetchall()
        finally:
            conn.close()

        return self._data_scope_rows(rows)

    @staticmethod
    def _data_scope_rows(
        rows: Sequence[Sequence[Any]],
    ) -> List[Dict[str, Any]]:
        scopes: List[Dict[str, Any]] = []
        for index_id, raw_metadata, raw_sheet_names in rows:
            metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
            scopes.append(
                {
                    "index_id": str(index_id),
                    "file_name": str(metadata.get("file_name") or index_id),
                    "workbook_hash": str(metadata.get("workbook_hash") or index_id),
                    "company_name": str(metadata.get("company_name") or ""),
                    "ticker": str(metadata.get("ticker") or ""),
                    "sheet_names": [
                        str(name) for name in (raw_sheet_names or []) if str(name).strip()
                    ],
                    "model": str(metadata.get("model") or DEFAULT_EMBEDDING_MODEL),
                    "dimension": int(metadata.get("dimension") or DEFAULT_EMBEDDING_DIMENSION),
                    "document_count": int(metadata.get("document_count") or 0),
                }
            )
        return scopes

    async def list_data_scopes_async(self) -> List[Dict[str, Any]]:
        """Return routing scopes through the native async PostgreSQL pool."""
        raw_url = getattr(self, "database_url", PGVECTOR_URL).replace(
            "postgresql+psycopg://",
            "postgresql://",
        )
        async with get_pooled_async_connection(raw_url) as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT
                        collection.name,
                        collection.cmetadata,
                        COALESCE(
                            ARRAY(
                                SELECT sheet.sheet_name
                                FROM sheets AS sheet
                                WHERE sheet.file_id = collection.cmetadata->>'workbook_hash'
                                  AND sheet.is_visible = TRUE
                                ORDER BY sheet.sheet_index, sheet.sheet_name
                            ),
                            ARRAY[]::text[]
                        ) AS sheet_names
                    FROM langchain_pg_collection AS collection
                    ORDER BY collection.name;
                    """
                )
                rows = await cursor.fetchall()
        return self._data_scope_rows(rows)

    def get_index_metadata(self, index_id: str) -> Dict[str, Any]:
        """Retrieve metadata dictionary for a pgvector collection."""
        try:
            return self.get_index_detail(index_id, limit=1)
        except Exception:
            return {}

    def get_index_detail(self, index_id: str, limit: int = 15) -> Dict[str, Any]:
        """Retrieve collection detail and sample document chunks."""
        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT c.uuid, c.name, c.cmetadata, COUNT(e.id) AS chunk_count
                    FROM langchain_pg_collection c
                    LEFT JOIN langchain_pg_embedding e ON c.uuid = e.collection_id
                    WHERE c.name = %s
                    GROUP BY c.uuid, c.name, c.cmetadata::text;
                    """,
                    (index_id,),
                )
                row = cur.fetchone()
                if not row:
                    raise PgVectorStoreError(f"pgvector 컬렉션을 찾을 수 없습니다: {index_id}")

                meta = self._json_mapping(row[2])

                cur.execute(
                    """
                    SELECT document, cmetadata
                    FROM langchain_pg_embedding
                    WHERE collection_id = %s
                    LIMIT %s;
                    """,
                    (row[0], limit),
                )
                chunk_rows = cur.fetchall()

                detected_tables_list = []
                sheet_names_list = []
                if meta.get("workbook_hash"):
                    cur.execute(
                        "SELECT sheet_name, detected_tables FROM sheets WHERE file_id = %s;",
                        (meta.get("workbook_hash"),),
                    )
                    sheet_rows = cur.fetchall()
                    for s_row in sheet_rows:
                        s_name = s_row[0]
                        sheet_names_list.append(s_name)
                        if s_row[1] and isinstance(s_row[1], list):
                            detected_tables_list.extend(s_row[1])
        finally:
            conn.close()

        sample_items = []
        for c in chunk_rows:
            text = c[0]
            cmeta = self._json_mapping(c[1])
            sample_items.append(
                {
                    "cell_id": cmeta.get("cell_id", ""),
                    "sheet_name": cmeta.get("sheet_name", ""),
                    "cell_coord": cmeta.get("cell_coord", ""),
                    "row_header": cmeta.get("row_header", []),
                    "column_header": cmeta.get("column_header", []),
                    "cell_value": cmeta.get("cell_value", ""),
                    "text": text,
                }
            )

        luna_output = None
        if detected_tables_list:
            luna_output = {
                "file_name": meta.get("file_name", ""),
                "workbook_hash": meta.get("workbook_hash", ""),
                "sheet_names": sheet_names_list,
                "tables": detected_tables_list,
            }

        return {
            "index_id": index_id,
            "file_name": meta.get("file_name", ""),
            "workbook_hash": meta.get("workbook_hash", ""),
            "company_name": meta.get("company_name", ""),
            "ticker": meta.get("ticker", ""),
            "model": meta.get("model", ""),
            "dimension": meta.get("dimension", DEFAULT_EMBEDDING_DIMENSION),
            "document_count": row[3],
            "created_at": meta.get("created_at") or datetime.now(timezone.utc).isoformat(),
            "storage": "PostgreSQL + pgvector",
            "duration_seconds": meta.get("duration_seconds"),
            "total_tokens": meta.get("total_tokens"),
            "estimated_cost_usd": meta.get("estimated_cost_usd"),
            "estimated_cost_krw": meta.get("estimated_cost_krw"),
            "batch_size": meta.get("batch_size"),
            "sample_items": sample_items,
            "sheet_names": sheet_names_list,
            "tables": detected_tables_list,
            "luna_output": luna_output,
        }

    def update_index_company(self, index_id: str, company_name: str) -> Dict[str, Any]:
        """Update company_name in collection metadata and cascade to all chunks and DB tables."""
        conn = None
        try:
            conn = self._raw_connection()
            with conn.cursor() as cur:
                # 1. Update langchain_pg_collection (cmetadata is column type json)
                cur.execute(
                    """
                    UPDATE langchain_pg_collection
                    SET cmetadata = jsonb_set(
                        COALESCE(cmetadata::jsonb, '{}'::jsonb),
                        '{company_name}',
                        to_jsonb(%s::text)
                    )::json
                    WHERE name = %s
                    RETURNING uuid, cmetadata;
                    """,
                    (company_name, index_id),
                )
                row = cur.fetchone()
                if not row:
                    raise PgVectorStoreError(f"pgvector 컬렉션을 찾을 수 없습니다: {index_id}")

                collection_uuid = row[0]
                col_meta = row[1] or {}
                if isinstance(col_meta, str):
                    import json

                    try:
                        col_meta = json.loads(col_meta)
                    except Exception:
                        col_meta = {}

                # 2. Update langchain_pg_embedding (cascade to all chunks in this collection)
                cur.execute(
                    """
                    UPDATE langchain_pg_embedding
                    SET cmetadata = jsonb_set(
                            COALESCE(cmetadata, '{}'::jsonb),
                            '{company_name}',
                            to_jsonb(%s::text)
                        ),
                        document = regexp_replace(
                            CASE
                                WHEN document ~ '^Company:\\s*[^|]*\\|\\s*'
                                    THEN document
                                ELSE 'Company: ? | ' || document
                            END,
                            '^Company:\\s*[^|]*\\|\\s*',
                            'Company: ' || %s || ' | '
                        )
                    WHERE collection_id = %s;
                    """,
                    (company_name, company_name, collection_uuid),
                )

            conn.commit()
        except PgVectorStoreError:
            raise
        except Exception as err:
            raise PgVectorStoreError(f"기업명 수정 실패: {err}") from err
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

        return self.get_index_detail(index_id)

    def ensure_optimized_indexes(self) -> None:
        """Create shared metadata and full-text indexes when they don't exist."""
        conn = None
        try:
            conn = self._raw_connection()
            if hasattr(conn, "autocommit"):
                conn.autocommit = True
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'langchain_pg_embedding';"
                    )
                    if cur.fetchone()[0] > 0:
                        self._drop_invalid_optimized_indexes(cur)
                        index_stmts = [
                            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_langchain_pg_embedding_cell_id ON langchain_pg_embedding ((cmetadata->>'cell_id'));",
                            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_langchain_pg_embedding_cell_coord_upper ON langchain_pg_embedding ((UPPER(cmetadata->>'cell_coord')));",
                            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_langchain_pg_embedding_workbook_hash ON langchain_pg_embedding ((cmetadata->>'workbook_hash'));",
                            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_langchain_pg_embedding_company_name ON langchain_pg_embedding ((cmetadata->>'company_name'));",
                            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_langchain_pg_embedding_sheet_name ON langchain_pg_embedding ((cmetadata->>'sheet_name'));",
                            """
                            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_langchain_pg_embedding_sheet_row
                            ON langchain_pg_embedding (
                                (cmetadata->>'sheet_name'),
                                ((cmetadata->>'row_index')::int)
                            )
                            WHERE cmetadata->>'row_index' ~ '^\\d+$';
                            """,
                            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_langchain_pg_embedding_collection_id ON langchain_pg_embedding (collection_id);",
                            """
                            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_langchain_pg_embedding_document_fts
                            ON langchain_pg_embedding
                            USING gin (to_tsvector('simple', document));
                            """,
                            """
                            CREATE INDEX IF NOT EXISTS idx_langchain_pg_embedding_cmetadata
                            ON langchain_pg_embedding
                            USING gin (cmetadata jsonb_path_ops);
                            """,
                        ]
                        for stmt in index_stmts:
                            try:
                                cur.execute(stmt)
                            except Exception as stmt_err:
                                logger.debug("Index creation notice: %s (%s)", stmt[:60], stmt_err)
            except Exception as error:
                logger.warning("pgvector 최적화 인덱스 생성 실패: %s", error)
                try:
                    with conn.cursor() as cur:
                        self._drop_invalid_optimized_indexes(cur)
                except Exception as cleanup_error:
                    logger.error(
                        "유효하지 않은 pgvector 최적화 인덱스 정리 실패: %s",
                        cleanup_error,
                    )
            finally:
                conn.close()
        except Exception as pool_error:
            logger.warning("ensure_optimized_indexes: 연결 풀 오류: %s", pool_error)
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    @staticmethod
    def _drop_invalid_optimized_indexes(cur: Any) -> None:
        """Drop invalid concurrent indexes so a later setup can rebuild them."""
        cur.execute(
            """
            SELECT index_class.relname
            FROM pg_catalog.pg_index AS index_state
            JOIN pg_catalog.pg_class AS index_class
              ON index_class.oid = index_state.indexrelid
            JOIN pg_catalog.pg_namespace AS index_namespace
              ON index_namespace.oid = index_class.relnamespace
            WHERE index_namespace.nspname = current_schema()
              AND index_class.relname = ANY(%s)
              AND NOT index_state.indisvalid;
            """,
            (list(_CONCURRENT_OPTIMIZED_INDEX_NAMES),),
        )
        invalid_index_names = [row[0] for row in cur.fetchall()]
        for index_name in invalid_index_names:
            if index_name not in _CONCURRENT_OPTIMIZED_INDEX_NAMES:
                continue
            cur.execute(f'DROP INDEX CONCURRENTLY IF EXISTS "{index_name}";')

    def delete(self, index_id: str) -> bool:
        """Delete a collection from pgvector.

        Returns:
            bool: True if deleted, False if not found.

        Raises:
            PgVectorStoreError: If database operation fails (not including not-found case).
        """
        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM langchain_pg_collection
                    WHERE name = %s
                    RETURNING uuid, cmetadata;
                    """,
                    (index_id,),
                )
                deleted_row = cur.fetchone()
            conn.commit()
        except Exception as error:
            conn.rollback()
            raise PgVectorStoreError(
                f"pgvector 컬렉션 삭제 중 데이터베이스 오류 발생: {error}"
            ) from error
        finally:
            conn.close()
        if deleted_row is None:
            return False
        with self._collection_uuid_lock:
            self._collection_uuid_cache.pop(index_id, None)
        metadata = deleted_row[1] if isinstance(deleted_row[1], dict) else {}
        dimension = int(metadata.get("dimension") or DEFAULT_EMBEDDING_DIMENSION)
        try:
            self._drop_collection_vector_index(str(deleted_row[0]), dimension)
        except Exception:
            logger.warning(
                "삭제된 컬렉션의 HNSW 인덱스 정리 실패: %s",
                index_id,
                exc_info=True,
            )
        return True

    def delete_by_workbook_hash(self, workbook_hash: str) -> int:
        """Logical cascade deletion: remove all collections matching a deleted workbook hash."""
        if not workbook_hash:
            return 0
        try:
            conn = self._raw_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        DELETE FROM langchain_pg_collection
                        WHERE cmetadata->>'workbook_hash' = %s
                        RETURNING name, uuid, cmetadata;
                        """,
                        (workbook_hash,),
                    )
                    deleted_rows = cur.fetchall()
                conn.commit()
            finally:
                conn.close()
            for collection_name, collection_uuid, raw_metadata in deleted_rows:
                with self._collection_uuid_lock:
                    self._collection_uuid_cache.pop(str(collection_name), None)
                metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
                dimension = int(metadata.get("dimension") or DEFAULT_EMBEDDING_DIMENSION)
                try:
                    self._drop_collection_vector_index(
                        str(collection_uuid),
                        dimension,
                    )
                except Exception:
                    logger.warning(
                        "삭제된 컬렉션의 HNSW 인덱스 정리 실패: %s",
                        collection_name,
                        exc_info=True,
                    )
            return len(deleted_rows)
        except Exception:
            return 0

    def list_registered_collections(self) -> List[Dict[str, Any]]:
        """List all indexed pgvector collections and metadata."""
        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT uuid, name, cmetadata FROM langchain_pg_collection ORDER BY name ASC;"
                )
                return [
                    {
                        "uuid": str(row[0]),
                        "name": str(row[1]),
                        "cmetadata": row[2] if isinstance(row[2], dict) else {},
                    }
                    for row in cur.fetchall()
                ]
        except Exception as err:
            logger.warning(f"list_registered_collections 실패: {err}")
            return []
        finally:
            conn.close()


__all__ = [
    "PgVectorCatalogMixin",
    "VECTOR_INDEX_STRATEGY",
    "VECTOR_PARTITION_STRATEGY",
]
