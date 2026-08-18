"""PostgreSQL + pgvector Storage Layer utilizing LangChain standard interfaces."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

import psycopg2
from langchain_core.documents import Document

from ..core.settings import PGVECTOR_URL
from ..embeddings.factory import EmbeddingEncoder
from ..spreadsheets.langchain_document import (
    cell_items_to_langchain_documents,
    langchain_document_to_cell_item,
)
from .vector_store_factory import get_langchain_connection_string, get_vector_store


class PgVectorStoreError(RuntimeError):
    """Raised when a pgvector database operation fails."""


class PgVectorStore:
    """Manages vector indexes in PostgreSQL using LangChain PGVector."""

    def __init__(self, database_url: str = PGVECTOR_URL) -> None:
        self.database_url = database_url

    def _raw_connection(self) -> psycopg2.extensions.connection:
        # Normalize to psycopg2 url
        raw_url = self.database_url.replace("postgresql+psycopg://", "postgresql://")
        return psycopg2.connect(raw_url)

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
        """Return connection details, versions, and LangChain collection statistics."""
        raw_url = self.database_url.replace("postgresql+psycopg://", "postgresql://")
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

                    cur.execute(
                        "SELECT extversion FROM pg_extension WHERE extname = 'vector';"
                    )
                    ext_row = cur.fetchone()
                    vector_version = ext_row[0] if ext_row else "not installed"

                    # Check LangChain collection tables
                    cur.execute(
                        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'langchain_pg_collection';"
                    )
                    has_collections = cur.fetchone()[0] > 0

                    total_indexes = 0
                    total_chunks = 0
                    if has_collections:
                        cur.execute("SELECT COUNT(*) FROM langchain_pg_collection;")
                        total_indexes = cur.fetchone()[0]
                        cur.execute("SELECT COUNT(*) FROM langchain_pg_embedding;")
                        total_chunks = cur.fetchone()[0]
            finally:
                conn.close()

            return {
                "connected": True,
                "host": safe_host,
                "port": port,
                "database": db_name,
                "postgres_version": pg_version.split()[1] if pg_version else "16",
                "pgvector_version": vector_version,
                "framework": "LangChain",
                "total_indexes": total_indexes,
                "total_chunks": total_chunks,
            }
        except Exception as err:
            return {
                "connected": False,
                "host": safe_host,
                "port": port,
                "database": db_name,
                "framework": "LangChain",
                "error": str(err),
                "total_indexes": 0,
                "total_chunks": 0,
            }

    def put_documents(
        self,
        index_id: str,
        documents: List[Document],
        model_name: str = "text-embedding-3-large",
        embedding_encoder: Optional[EmbeddingEncoder] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add standardized LangChain Document objects to pgvector."""
        if not documents:
            return

        clean_meta = {
            "file_name": (metadata or {}).get("file_name", ""),
            "workbook_hash": (metadata or {}).get("workbook_hash", ""),
            "model": (metadata or {}).get("model", model_name),
            "dimension": (metadata or {}).get("dimension", 3072),
            "document_count": len(documents),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "pipeline": (metadata or {}).get("pipeline", "luna_vlm_structured"),
        }

        store = get_vector_store(
            collection_name=index_id,
            backend="pgvector",
            model_name=model_name,
            embedding_encoder=embedding_encoder,
            collection_metadata=clean_meta,
            database_url=self.database_url,
        )

        # Pre-delete existing collection to replace clean
        try:
            store.delete_collection()
        except Exception:
            pass

        # Ensure collection is created with metadata
        try:
            store.create_collection()
        except Exception:
            pass

        store.add_documents(documents)

        # Also execute direct update for guarantee
        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE langchain_pg_collection
                    SET cmetadata = %s
                    WHERE name = %s;
                    """,
                    (psycopg2.extras.Json(clean_meta), index_id),
                )
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            conn.close()

        self.ensure_optimized_indexes()

    def put(
        self,
        index_id: str,
        vectors_or_items: Any,
        metadata: Dict[str, Any],
        embedding_encoder: Optional[EmbeddingEncoder] = None,
    ) -> None:
        """Backwards-compatible put: converts cell items to LangChain documents and inserts."""
        raw_items = metadata.get("items") or []
        model_name = metadata.get("model", "text-embedding-3-large")
        file_name = metadata.get("file_name", "")
        workbook_hash = metadata.get("workbook_hash", "")

        docs = cell_items_to_langchain_documents(
            items=raw_items,
            file_name=file_name,
            workbook_hash=workbook_hash,
            index_id=index_id,
        )
        self.put_documents(
            index_id=index_id,
            documents=docs,
            model_name=model_name,
            embedding_encoder=embedding_encoder,
            metadata=metadata,
        )

    def list_indexes(self) -> List[Dict[str, Any]]:
        """List all collections registered in pgvector via LangChain."""
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
                    SELECT c.name, c.cmetadata, COUNT(e.id) AS chunk_count
                    FROM langchain_pg_collection c
                    LEFT JOIN langchain_pg_embedding e ON c.uuid = e.collection_id
                    GROUP BY c.uuid;
                    """
                )
                rows = cur.fetchall()

            results = []
            for r in rows:
                name = r[0]
                meta = r[1] or {}
                if isinstance(meta, str):
                    import json
                    try:
                        meta = json.loads(meta)
                    except Exception:
                        meta = {}
                count = r[2]
                results.append({
                    "index_id": name,
                    "file_name": meta.get("file_name", "unknown"),
                    "workbook_hash": meta.get("workbook_hash", ""),
                    "model": meta.get("model", "text-embedding-3-large"),
                    "dimension": meta.get("dimension", 3072),
                    "document_count": count,
                    "created_at": meta.get("created_at") or datetime.now(timezone.utc).isoformat(),
                    "storage": "pgvector (LangChain)",
                })
            return results
        finally:
            conn.close()

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

                meta = row[2] or {}
                if isinstance(meta, str):
                    import json
                    try:
                        meta = json.loads(meta)
                    except Exception:
                        meta = {}

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

            sample_items = []
            for c in chunk_rows:
                text = c[0]
                cmeta = c[1] or {}
                if isinstance(cmeta, str):
                    import json
                    try:
                        cmeta = json.loads(cmeta)
                    except Exception:
                        cmeta = {}
                sample_items.append({
                    "cell_id": cmeta.get("cell_id", ""),
                    "sheet_name": cmeta.get("sheet_name", ""),
                    "cell_coord": cmeta.get("cell_coord", ""),
                    "row_header": cmeta.get("row_header", []),
                    "column_header": cmeta.get("column_header", []),
                    "cell_value": cmeta.get("cell_value", ""),
                    "text": text,
                })

            return {
                "index_id": index_id,
                "file_name": meta.get("file_name", ""),
                "workbook_hash": meta.get("workbook_hash", ""),
                "model": meta.get("model", ""),
                "dimension": meta.get("dimension", 3072),
                "document_count": row[3],
                "storage": "pgvector (LangChain)",
                "sample_items": sample_items,
            }
        finally:
            conn.close()

    def ensure_optimized_indexes(self) -> None:
        """Create HNSW vector index and jsonb_path_ops GIN metadata index if they don't exist."""
        try:
            conn = self._raw_connection()
            conn.autocommit = True
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'langchain_pg_embedding';"
                    )
                    if cur.fetchone()[0] > 0:
                        cur.execute(
                            """
                            CREATE INDEX IF NOT EXISTS idx_langchain_pg_embedding_hnsw
                            ON langchain_pg_embedding
                            USING hnsw (embedding vector_cosine_ops);
                            """
                        )
                        cur.execute(
                            """
                            CREATE INDEX IF NOT EXISTS idx_langchain_pg_embedding_cmetadata
                            ON langchain_pg_embedding
                            USING gin (cmetadata jsonb_path_ops);
                            """
                        )
            finally:
                conn.close()
        except Exception:
            pass

    def delete(self, index_id: str) -> bool:
        """Delete a collection from pgvector."""
        try:
            conn = self._raw_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM langchain_pg_collection WHERE name = %s RETURNING name;",
                        (index_id,),
                    )
                    deleted = cur.fetchone() is not None
                conn.commit()
                return deleted
            except Exception:
                conn.rollback()
                return False
            finally:
                conn.close()
        except Exception:
            return False

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
                        RETURNING name;
                        """,
                        (workbook_hash,),
                    )
                    deleted_rows = cur.fetchall()
                conn.commit()
                return len(deleted_rows)
            except Exception:
                conn.rollback()
                return 0
            finally:
                conn.close()
        except Exception:
            return 0

    def search(
        self,
        index_id: str,
        query_text: str,
        model_name: str = "text-embedding-3-large",
        embedding_encoder: Optional[EmbeddingEncoder] = None,
        limit: int = 5,
    ) -> List[Tuple[float, Dict[str, Any]]]:
        """Perform LangChain similarity search with score (Cosine distance)."""
        store = get_vector_store(
            collection_name=index_id,
            backend="pgvector",
            model_name=model_name,
            embedding_encoder=embedding_encoder,
            database_url=self.database_url,
        )

        hits = store.similarity_search_with_score(query_text, k=limit)
        results = []
        for doc, score in hits:
            # LangChain cosine distance is distance (0 = identical, 1 = orthogonal, 2 = opposite)
            similarity = max(0.0, 1.0 - float(score))
            cell_item = langchain_document_to_cell_item(doc, score=similarity)
            results.append((similarity, cell_item))
        return results
