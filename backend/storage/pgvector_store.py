"""PostgreSQL + pgvector Storage Layer utilizing LangChain standard interfaces."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import logging
from typing import Any, Callable, Dict, Generator, List, Optional, Sequence, Tuple
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


logger = logging.getLogger(__name__)


class PgVectorStoreError(RuntimeError):
    """Raised when a pgvector database operation fails."""


PGVECTOR_INSERT_BATCH_SIZE = 1000


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
        Add documents to a pgvector collection, replacing any existing collection with the same identifier.
        
        Parameters:
            index_id (str): Identifier of the collection to replace.
            documents (List[Document]): Documents to store.
            model_name (str): Embedding model name used when embeddings are generated.
            embedding_encoder (Optional[EmbeddingEncoder]): Encoder used to generate embeddings.
            metadata (Optional[Dict[str, Any]]): Collection metadata.
            vectors (Optional[Any]): Precomputed vectors corresponding to every document.
            progress_callback (Optional[Callable[[Dict[str, int]], None]]): Callback receiving batch and item progress.
        
        Raises:
            PgVectorStoreError: If document insertion fails.
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

        # SQLAlchemy expands each embedding row into several bind parameters.
        # Sending an entire large workbook at once crosses psycopg's 65,535
        # parameter protocol limit, so persist bounded batches explicitly.
        total_items = len(documents)
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
                if vectors is not None and len(vectors) == total_items:
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
            if isinstance(resolved_vectors, (list, tuple))
            or (
                hasattr(resolved_vectors, "__len__")
                and not isinstance(resolved_vectors, (dict, str, bytes))
            )
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
                            CREATE INDEX IF NOT EXISTS idx_langchain_pg_embedding_cell_id
                            ON langchain_pg_embedding ((cmetadata->>'cell_id'));
                            """
                        )
                        cur.execute(
                            """
                            CREATE INDEX IF NOT EXISTS idx_langchain_pg_embedding_cell_coord_upper
                            ON langchain_pg_embedding ((UPPER(cmetadata->>'cell_coord')));
                            """
                        )
                        cur.execute(
                            """
                            CREATE INDEX IF NOT EXISTS idx_langchain_pg_embedding_workbook_hash
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
        """
        Perform vector similarity search within a pgvector collection.
        
        Parameters:
            collection_name (str): Name of the collection to search.
            embedding (List[float]): Query embedding vector.
            k (int): Maximum number of results to retrieve.
        
        Returns:
            List[Tuple[Any, float]]: Document and cosine-distance pairs, or an empty list if the collection is unavailable or the search fails.
        """
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

    def fetch_cells_by_metadata(
        self,
        cell_identifiers: List[str],
        workbook_hash: Optional[str] = None,
        collection_name: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Fetch cell documents matching the provided identifiers, optionally filtered by workbook or collection.
        
        Parameters:
            cell_identifiers (List[str]): Cell IDs, coordinates, or strings containing coordinate-like values.
            workbook_hash (Optional[str]): Restricts results to a workbook with this hash.
            collection_name (Optional[str]): Restricts results to this collection.
            limit (int): Maximum number of matching cells to return.
        
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

                # We search matching cell_id, cell_coord, or cell_id ILIKE pattern
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

                query = """
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
                        cmetadata->>'company_name' AS company_name
                    FROM langchain_pg_embedding
                    WHERE (
                        cmetadata->>'cell_id' = ANY(%s)
                        OR cmetadata->>'cell_coord' = ANY(%s)
                        OR UPPER(cmetadata->>'cell_coord') = ANY(%s)
                    )
                """
                params: List[Any] = [clean_ids, all_search_targets, all_search_targets]

                if col_uuid:
                    query += " AND collection_id = %s"
                    params.append(col_uuid)
                elif workbook_hash:
                    query += " AND cmetadata->>'workbook_hash' = %s"
                    params.append(workbook_hash)

                query += " LIMIT %s;"
                params.append(limit)

                cur.execute(query, tuple(params))
                rows = cur.fetchall()

            import json
            results = []
            seen_coords = set()
            for r in rows:
                _id, text, _cmeta, cell_id, cell_coord, sheet_name, cell_value, row_header, col_header, company_name = r
                key = (sheet_name, cell_coord)
                if key in seen_coords:
                    continue
                seen_coords.add(key)

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
