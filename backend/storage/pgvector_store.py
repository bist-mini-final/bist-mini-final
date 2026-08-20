"""PostgreSQL + pgvector Storage Layer utilizing LangChain standard interfaces."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import logging
from numbers import Real
from typing import Any, Callable, Dict, Generator, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

import psycopg2
import psycopg2.extras
from langchain_core.documents import Document

from ..core.settings import PGVECTOR_URL
from ..embeddings.factory import EmbeddingEncoder
from ..spreadsheets.langchain_document import (
    cell_items_to_langchain_documents,
    langchain_document_to_cell_item,
)
from .vector_store_factory import get_langchain_connection_string, get_vector_store


logger = logging.getLogger(__name__)


class PgVectorStoreError(RuntimeError):
    """Raised when a pgvector database operation fails."""


PGVECTOR_INSERT_BATCH_SIZE = 1000
_CONCURRENT_OPTIMIZED_INDEX_NAMES = (
    "idx_langchain_pg_embedding_cell_id",
    "idx_langchain_pg_embedding_cell_coord_upper",
    "idx_langchain_pg_embedding_workbook_hash",
)


def _is_numeric_vector_collection(candidate: Any) -> bool:
    """Return whether a candidate is a non-empty sequence of numeric vectors."""
    if isinstance(candidate, (dict, str, bytes)) or not hasattr(candidate, "__len__"):
        return False
    try:
        vectors = list(candidate)
    except TypeError:
        return False
    if not vectors:
        return False
    for vector in vectors:
        if isinstance(vector, (dict, str, bytes)) or not hasattr(vector, "__len__"):
            return False
        try:
            values = list(vector)
        except TypeError:
            return False
        if not values or not all(
            isinstance(value, Real) and not isinstance(value, bool)
            for value in values
        ):
            return False
    return True


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
        vectors: Optional[Any] = None,
        progress_callback: Optional[Callable[[Dict[str, int]], None]] = None,
    ) -> None:
        """
        Store documents in a pgvector collection, replacing any existing collection with the same identifier.
        
        Parameters:
            index_id (str): Identifier of the collection to replace.
            documents (List[Document]): Documents to store.
            model_name (str): Embedding model to use when generating vectors.
            embedding_encoder (Optional[EmbeddingEncoder]): Encoder for generating embeddings.
            metadata (Optional[Dict[str, Any]]): Metadata to associate with the collection.
            vectors (Optional[Any]): Precomputed vectors corresponding to all documents.
            progress_callback (Optional[Callable[[Dict[str, int]], None]]): Callback receiving batch and item progress.
        
        Raises:
            PgVectorStoreError: If inserting a document batch fails.
        """
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

        # Validate vectors length BEFORE modifying the collection
        total_items = len(documents)
        use_precomputed_vectors = False
        if vectors is not None:
            if len(vectors) != total_items:
                raise PgVectorStoreError(
                    f"사전 계산된 벡터 개수({len(vectors)})가 문서 개수({total_items})와 일치하지 않습니다."
                )
            use_precomputed_vectors = True

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
        except Exception as delete_error:
            logger.error(
                "기존 pgvector 컬렉션('%s') 삭제 실패: %s",
                index_id,
                delete_error,
                exc_info=True,
            )
            raise PgVectorStoreError(
                f"기존 pgvector 컬렉션('{index_id}') 삭제 실패: {delete_error}"
            ) from delete_error

        # Ensure collection is created with metadata
        try:
            store.create_collection()
        except Exception as create_error:
            logger.error(
                "pgvector 컬렉션('%s') 생성 실패: %s",
                index_id,
                create_error,
                exc_info=True,
            )
            raise PgVectorStoreError(
                f"pgvector 컬렉션('{index_id}') 생성 실패: {create_error}"
            ) from create_error

        # SQLAlchemy expands each embedding row into several bind parameters.
        # Sending an entire large workbook at once crosses psycopg's 65,535
        # parameter protocol limit, so persist bounded batches explicitly.

        total_batches = max(
            1,
            (total_items + PGVECTOR_INSERT_BATCH_SIZE - 1)
            // PGVECTOR_INSERT_BATCH_SIZE,
        )
        if progress_callback is not None:
            progress_callback(
                {
                    "completed_batches": 0,
                    "total_batches": total_batches,
                    "completed_items": 0,
                    "total_items": total_items,
                }
            )
        try:
            for batch_index, start in enumerate(
                range(0, total_items, PGVECTOR_INSERT_BATCH_SIZE),
                start=1,
            ):
                stop = min(start + PGVECTOR_INSERT_BATCH_SIZE, total_items)
                document_batch = documents[start:stop]
                if use_precomputed_vectors:
                    vector_batch = vectors[start:stop]
                    texts = [doc.page_content for doc in document_batch]
                    metadatas = [doc.metadata for doc in document_batch]
                    vec_list = [
                        vector.tolist() if hasattr(vector, "tolist") else list(vector)
                        for vector in vector_batch
                    ]
                    store.add_embeddings(
                        texts=texts,
                        embeddings=vec_list,
                        metadatas=metadatas,
                    )
                else:
                    store.add_documents(document_batch)
                if progress_callback is not None:
                    progress_callback(
                        {
                            "completed_batches": batch_index,
                            "total_batches": total_batches,
                            "completed_items": stop,
                            "total_items": total_items,
                        }
                    )
        except Exception as error:
            # A failed write must not leave a queryable partial collection.
            try:
                store.delete_collection()
            except Exception:
                pass
            error_message = str(error)
            for marker in ("\n[SQL:", " [SQL:"):
                if marker in error_message:
                    error_message = error_message.split(marker, 1)[0].rstrip()
                    break
            raise PgVectorStoreError(
                "pgvector 문서 배치 적재 실패 "
                f"({batch_index}/{total_batches}): {error_message[:2000]}"
            ) from error

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
            logger.warning(
                "langchain_pg_collection 메타데이터 직접 업데이트 실패: %s",
                index_id,
                exc_info=True,
            )
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
        progress_callback: Optional[Callable[[Dict[str, int]], None]] = None,
    ) -> None:
        """
        Insert spreadsheet cell items into a vector collection.
        
        Parameters:
            vectors_or_items (Any): Cell items or precomputed vectors to use when inserting documents.
            metadata (Optional[Dict[str, Any]]): Collection and workbook metadata, including the cell items.
            progress_callback (Optional[Callable[[Dict[str, int]], None]]): Callback receiving insertion progress updates.
        """
        meta_dict = metadata or {}
        raw_items = meta_dict.get("items") or []
        model_name = meta_dict.get("model", "text-embedding-3-large")
        file_name = meta_dict.get("file_name", "")
        workbook_hash = meta_dict.get("workbook_hash", "")
        company_name = meta_dict.get("company_name", "")

        resolved_vectors = vectors if vectors is not None else vectors_or_items
        usable_vectors = (
            resolved_vectors
            if _is_numeric_vector_collection(resolved_vectors)
            else None
        )

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
            vectors=usable_vectors,
            progress_callback=progress_callback,
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
        conn = None
        try:
            conn = self._raw_connection()
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'langchain_pg_embedding';"
                )
                if cur.fetchone()[0] > 0:
                    self._drop_invalid_optimized_indexes(cur)
                    cur.execute(
                        """
                        CREATE INDEX IF NOT EXISTS idx_langchain_pg_embedding_hnsw
                        ON langchain_pg_embedding
                        USING hnsw (embedding vector_cosine_ops);
                        """
                    )
                    cur.execute(
                        """
                        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_langchain_pg_embedding_cell_id
                        ON langchain_pg_embedding ((cmetadata->>'cell_id'));
                        """
                    )
                    cur.execute(
                        """
                        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_langchain_pg_embedding_cell_coord_upper
                        ON langchain_pg_embedding ((UPPER(cmetadata->>'cell_coord')));
                        """
                    )
                    cur.execute(
                        """
                        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_langchain_pg_embedding_workbook_hash
                        ON langchain_pg_embedding ((cmetadata->>'workbook_hash'));
                        """
                    )
                    cur.execute(
                        """
                        CREATE INDEX IF NOT EXISTS idx_langchain_pg_embedding_cmetadata
                        ON langchain_pg_embedding
                        USING gin (cmetadata jsonb_path_ops);
                        """
                    )
        except Exception as error:
            logger.warning("pgvector 최적화 인덱스 생성 실패: %s", error)
            if conn is not None:
                try:
                    with conn.cursor() as cur:
                        self._drop_invalid_optimized_indexes(cur)
                except Exception as cleanup_error:
                    logger.error(
                        "유효하지 않은 pgvector 최적화 인덱스 정리 실패: %s",
                        cleanup_error,
                    )
        finally:
            if conn is not None:
                conn.close()

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
        """
        Search a pgvector collection using an embedding vector.

        Parameters:
            collection_name (str): Name of the collection to search.
            embedding (List[float]): Query embedding vector.
            k (int): Maximum number of results to return.

        Returns:
            List[Tuple[Any, float]]: Document and cosine-distance pairs, or an empty list if the collection does not exist.

        Raises:
            PgVectorStoreError: If both direct SQL and fallback similarity searches fail.
        """
        conn = None
        try:
            conn = self._raw_connection()
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
                    id=str(_id),
                )
                results.append((doc, float(dist) if dist is not None else 0.0))
            return results
        except Exception as error:
            logger.warning(
                "직접 SQL 벡터 유사도 검색 실패 (%s): %s",
                collection_name,
                error,
                exc_info=True,
            )
            try:
                store = get_vector_store(
                    collection_name=collection_name,
                    backend="pgvector",
                    database_url=self.database_url,
                )
                return store.similarity_search_with_score_by_vector(embedding, k=k)
            except Exception as fallback_error:
                logger.warning(
                    "폴백 PGVector 유사도 검색 실패 (%s): %s",
                    collection_name,
                    fallback_error,
                    exc_info=True,
                )
                raise PgVectorStoreError(
                    f"PostgreSQL pgvector 유사도 검색 실패 ({collection_name}): {fallback_error}"
                ) from fallback_error
        finally:
            if conn is not None:
                conn.close()

    def fetch_cells_by_metadata(
        self,
        cell_identifiers: List[str],
        workbook_hash: Optional[str] = None,
        collection_name: Optional[str] = None,
        limit: int = 50,
        cell_references: Optional[List[Dict[str, Optional[str]]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch cell documents matching the provided identifiers, optionally filtered by workbook or collection.
        
        Parameters:
            cell_identifiers (List[str]): Cell IDs, coordinates, or strings containing coordinate-like values.
            workbook_hash (Optional[str]): Restricts results to a workbook with this hash.
            collection_name (Optional[str]): Restricts results to this collection.
            limit (int): Maximum number of matching cells to return.
            cell_references (Optional[List[Dict[str, Optional[str]]]]): Structured
                coordinate filters whose optional ``sheet_name`` is matched together
                with the coordinate.
        
        Returns:
            List[Dict[str, Any]]: Normalized cell records containing identifiers, values, headers, source text, and company metadata. Returns an empty list when the input is empty or retrieval fails.
        """
        if not cell_identifiers or (not workbook_hash and not collection_name):
            if cell_identifiers:
                logger.warning(
                    "직접 셀 메타데이터 조회를 거부했습니다: collection_name 또는 workbook_hash가 필요합니다"
                )
            return []

        clean_ids = [cid.strip() for cid in cell_identifiers if cid and cid.strip()]
        if not clean_ids:
            return []

        conn = self._raw_connection()
        try:
            with conn.cursor() as cur:
                col_uuid = None
                if collection_name:
                    cur.execute(
                        "SELECT uuid FROM langchain_pg_collection WHERE name = %s;",
                        (collection_name,),
                    )
                    row = cur.fetchone()
                    if row:
                        col_uuid = row[0]
                    elif not workbook_hash:
                        return []

                # Legacy callers search matching cell IDs or coordinates. Structured
                # references keep qualified sheet/coordinate pairs together.
                extracted_coords = []
                for cid in clean_ids:
                    parts = cid.replace(":", " ").replace("!", " ").split()
                    for p in parts:
                        p_clean = p.strip()
                        if p_clean and p_clean[0].isalpha() and any(ch.isdigit() for ch in p_clean):
                            extracted_coords.append(p_clean.upper())

                all_search_targets = list(
                    dict.fromkeys(item.upper() for item in clean_ids + extracted_coords)
                )

                where_clauses: List[str] = []
                params: List[Any] = []
                if cell_references is None:
                    where_clauses.append(
                        """(
                            cmetadata->>'cell_id' = ANY(%s)
                            OR cmetadata->>'cell_coord' = ANY(%s)
                            OR UPPER(cmetadata->>'cell_coord') = ANY(%s)
                        )"""
                    )
                    params.extend([clean_ids, all_search_targets, all_search_targets])
                else:
                    qualified_sheets: List[str] = []
                    qualified_coords: List[str] = []
                    unqualified_coords: List[str] = []
                    for reference in cell_references:
                        coord = str(reference.get("cell_coord") or "").strip().upper()
                        if not coord:
                            continue
                        sheet_name = str(reference.get("sheet_name") or "").strip()
                        if sheet_name:
                            qualified_sheets.append(sheet_name.upper())
                            qualified_coords.append(coord)
                        else:
                            unqualified_coords.append(coord)
                    if unqualified_coords:
                        where_clauses.append("UPPER(cmetadata->>'cell_coord') = ANY(%s)")
                        params.append(list(dict.fromkeys(unqualified_coords)))
                    if qualified_coords:
                        where_clauses.append(
                            """EXISTS (
                                SELECT 1
                                FROM unnest(%s::text[], %s::text[])
                                    AS reference(sheet_name, cell_coord)
                                WHERE UPPER(cmetadata->>'sheet_name') = reference.sheet_name
                                  AND UPPER(cmetadata->>'cell_coord') = reference.cell_coord
                            )"""
                        )
                        params.extend([qualified_sheets, qualified_coords])
                    if not where_clauses:
                        return []

                query = f"""
                    WITH ranked_cells AS (
                    SELECT
                        id,
                        document,
                        cmetadata,
                        cmetadata->>'cell_id' AS cell_id,
                        cmetadata->>'cell_coord' AS cell_coord,
                        cmetadata->>'sheet_name' AS sheet_name,
                        cmetadata->>'cell_value' AS cell_value,
                        cmetadata->'row_header' AS row_header,
                        cmetadata->'column_header' AS column_header,
                        cmetadata->>'company_name' AS company_name,
                        ROW_NUMBER() OVER (
                            PARTITION BY
                                UPPER(cmetadata->>'sheet_name'),
                                UPPER(cmetadata->>'cell_coord')
                            ORDER BY
                                CASE cmetadata->>'variant'
                                    WHEN 'header_with_value' THEN 0
                                    WHEN 'header_only' THEN 1
                                    ELSE 2
                                END,
                                COALESCE(cmetadata->'row_header', '[]'::jsonb)::text,
                                COALESCE(cmetadata->'column_header', '[]'::jsonb)::text,
                                COALESCE(document, ''),
                                id
                        ) AS cell_rank
                    FROM langchain_pg_embedding
                    WHERE ({' OR '.join(where_clauses)})
                """

                if col_uuid:
                    query += " AND collection_id = %s"
                    params.append(col_uuid)
                elif workbook_hash:
                    query += " AND cmetadata->>'workbook_hash' = %s"
                    params.append(workbook_hash)

                query += """
                    )
                    SELECT
                        id,
                        document,
                        cmetadata,
                        cell_id,
                        cell_coord,
                        sheet_name,
                        cell_value,
                        row_header,
                        column_header,
                        company_name
                    FROM ranked_cells
                    WHERE cell_rank = 1
                    ORDER BY UPPER(sheet_name), UPPER(cell_coord), id
                    LIMIT %s;
                """
                params.append(limit)

                cur.execute(query, tuple(params))
                rows = cur.fetchall()

            import json
            results = []
            for r in rows:
                _id, text, _cmeta, cell_id, cell_coord, sheet_name, cell_value, row_header, col_header, company_name = r
                if isinstance(row_header, str):
                    try:
                        row_header = json.loads(row_header)
                    except Exception:
                        pass
                if isinstance(col_header, str):
                    try:
                        col_header = json.loads(col_header)
                    except Exception:
                        pass

                results.append({
                    "cell_id": cell_id or f"{sheet_name}:{cell_coord}",
                    "cell_coord": cell_coord,
                    "sheet_name": sheet_name,
                    "cell_value": cell_value,
                    "row_header": row_header if isinstance(row_header, list) else ([row_header] if row_header else []),
                    "column_header": col_header if isinstance(col_header, list) else ([col_header] if col_header else []),
                    "company_name": company_name,
                    "source_text": text,
                })
            return results
        except Exception:
            logger.exception("직접 셀 메타데이터 조회 실패")
            return []
        finally:
            conn.close()
