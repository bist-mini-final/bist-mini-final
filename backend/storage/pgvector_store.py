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

        meta_dict = metadata or {}
        clean_meta = {
            "file_name": meta_dict.get("file_name", ""),
            "workbook_hash": meta_dict.get("workbook_hash", ""),
            "model": meta_dict.get("model", model_name),
            "dimension": meta_dict.get("dimension", 3072),
            "document_count": len(documents),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "pipeline": meta_dict.get("pipeline", "luna_vlm_structured"),
            "duration_seconds": meta_dict.get("duration_seconds"),
            "total_tokens": meta_dict.get("total_tokens"),
            "estimated_cost_usd": meta_dict.get("estimated_cost_usd"),
            "estimated_cost_krw": meta_dict.get("estimated_cost_krw"),
            "batch_size": meta_dict.get("batch_size"),
            "company_name": meta_dict.get("company_name", ""),
            "ticker": meta_dict.get("ticker", ""),
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
        vectors_or_items: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
        embedding_encoder: Optional[EmbeddingEncoder] = None,
        vectors: Any = None,
    ) -> None:
        """Backwards-compatible put: converts cell items to LangChain documents and inserts."""
        meta_dict = metadata or {}
        raw_items = meta_dict.get("items") or []
        model_name = meta_dict.get("model", "text-embedding-3-large")
        file_name = meta_dict.get("file_name", "")
        workbook_hash = meta_dict.get("workbook_hash", "")
        company_name = meta_dict.get("company_name", "")

        docs = cell_items_to_langchain_documents(
            items=raw_items,
            file_name=file_name,
            workbook_hash=workbook_hash,
            index_id=index_id,
            company_name=company_name,
        )
        self.put_documents(
            index_id=index_id,
            documents=docs,
            model_name=model_name,
            embedding_encoder=embedding_encoder,
            metadata=metadata,
        )

    def list_indexes(self) -> List[Dict[str, Any]]:
        """
        List all collections registered in the LangChain pgvector storage.
        
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
                    SELECT c.name, c.cmetadata, COUNT(e.id) AS chunk_count
                    FROM langchain_pg_collection c
                    LEFT JOIN langchain_pg_embedding e ON c.uuid = e.collection_id
                    GROUP BY c.name, c.uuid, c.cmetadata::text;
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
                    "company_name": meta.get("company_name", ""),
                    "ticker": meta.get("ticker", ""),
                    "model": meta.get("model", "text-embedding-3-large"),
                    "dimension": meta.get("dimension", 3072),
                    "document_count": count,
                    "created_at": meta.get("created_at") or datetime.now(timezone.utc).isoformat(),
                    "storage": "pgvector (LangChain)",
                    "duration_seconds": meta.get("duration_seconds"),
                    "total_tokens": meta.get("total_tokens"),
                    "estimated_cost_usd": meta.get("estimated_cost_usd"),
                    "estimated_cost_krw": meta.get("estimated_cost_krw"),
                    "batch_size": meta.get("batch_size"),
                })
            return results
        finally:
            conn.close()

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

                detected_tables_list = []
                sheet_names_list = []
                if meta.get("workbook_hash"):
                    cur.execute(
                        "SELECT sheet_name, detected_tables FROM sheets WHERE file_id = %s;",
                        (meta.get("workbook_hash"),)
                    )
                    sheet_rows = cur.fetchall()
                    for s_row in sheet_rows:
                        s_name = s_row[0]
                        sheet_names_list.append(s_name)
                        if s_row[1] and isinstance(s_row[1], list):
                            detected_tables_list.extend(s_row[1])

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
                "dimension": meta.get("dimension", 3072),
                "document_count": row[3],
                "created_at": meta.get("created_at") or datetime.now(timezone.utc).isoformat(),
                "storage": "pgvector (LangChain)",
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
        finally:
            conn.close()

    def update_index_company(self, index_id: str, company_name: str) -> Dict[str, Any]:
        """Update company_name in collection metadata and cascade to all chunks and DB tables."""
        conn = self._raw_connection()
        try:
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
                workbook_hash = col_meta.get("workbook_hash", "")

                # 2. Update langchain_pg_embedding (cascade to all chunks in this collection)
                cur.execute(
                    """
                    UPDATE langchain_pg_embedding
                    SET cmetadata = jsonb_set(
                        COALESCE(cmetadata, '{}'::jsonb),
                        '{company_name}',
                        to_jsonb(%s::text)
                    )
                    WHERE collection_id = %s;
                    """,
                    (company_name, collection_uuid),
                )

            conn.commit()
        except Exception as err:
            conn.rollback()
            raise PgVectorStoreError(f"기업명 수정 실패: {err}") from err
        finally:
            conn.close()

        return self.get_index_detail(index_id)

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

    def similarity_search_by_vector_with_score(
        self,
        collection_name: str,
        embedding: List[float],
        k: int = 10,
    ) -> List[Tuple[Any, float]]:
        """Perform vector similarity search on PostgreSQL pgvector with cosine operator (<=>)."""
        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT uuid FROM langchain_pg_collection WHERE name = %s;",
                    (collection_name,),
                )
                row = cur.fetchone()
                if not row:
                    return []
                col_uuid = row[0]

                cur.execute(
                    """
                    SELECT id, document, cmetadata, (embedding <=> %s::vector) AS distance
                    FROM langchain_pg_embedding
                    WHERE collection_id = %s
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s;
                    """,
                    (embedding, col_uuid, embedding, k),
                )
                rows = cur.fetchall()

            from langchain_core.documents import Document
            results = []
            for r in rows:
                _id, text, cmeta, dist = r
                if isinstance(cmeta, str):
                    import json
                    try:
                        cmeta = json.loads(cmeta)
                    except Exception:
                        cmeta = {}
                doc = Document(
                    page_content=text,
                    metadata=cmeta or {},
                )
                results.append((doc, float(dist) if dist is not None else 0.0))
            return results
        except Exception:
            try:
                store = get_vector_store(
                    collection_name=collection_name,
                    backend="pgvector",
                    database_url=self.database_url,
                )
                return store.similarity_search_by_vector_with_score(embedding, k=k)
            except Exception:
                return []
        finally:
            conn.close()
