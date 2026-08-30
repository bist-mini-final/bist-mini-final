"""Native psycopg storage adapter for PostgreSQL and pgvector."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from numbers import Real
from typing import Any, Callable, Dict, List, Optional, Sequence
from urllib.parse import urlparse
from uuid import UUID, uuid4, uuid5

import psycopg2.extras
from langchain_core.documents import Document

from backend.contracts.vector import PgVectorReplacePlan
from backend.core.settings import PGVECTOR_URL
from backend.providers.embeddings.ports import EmbeddingEncoder
from backend.storage.embedding_artifacts import EmbeddingArtifactVectors
from backend.storage.pgvector_binary_copy import copy_documents
from backend.storage.pgvector_errors import PgVectorStoreError
from backend.storage.repositories.pgvector_retrieval import PgVectorRetrievalMixin
from backend.storage.spreadsheets.langchain_document import cell_items_to_langchain_documents
from modules.common.config import DEFAULT_EMBEDDING_DIMENSION, DEFAULT_EMBEDDING_MODEL

from .connection_pool import get_pooled_async_connection, get_pooled_raw_connection

logger = logging.getLogger(__name__)


PGVECTOR_INSERT_BATCH_SIZE = 1000
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
            isinstance(value, Real) and not isinstance(value, bool) for value in values
        ):
            return False
    return True


class PgVectorStore(PgVectorRetrievalMixin):
    """Manage pgvector collections through the shared psycopg connection pool."""

    @staticmethod
    def index_id(artifact_id: str) -> str:
        """Derive standard pgvector collection index identifier from an artifact ID."""
        return f"idx_{artifact_id}"

    def __init__(self, database_url: str = PGVECTOR_URL) -> None:
        self.database_url = database_url
        self._collection_uuid_cache: Dict[str, str] = {}
        self._collection_uuid_lock = threading.Lock()

    def _raw_connection(self) -> Any:
        raw_url = getattr(self, "database_url", PGVECTOR_URL).replace(
            "postgresql+psycopg://", "postgresql://"
        )
        return get_pooled_raw_connection(raw_url)

    def _read_connection(self) -> Any:
        """Borrow an autocommit connection so SELECTs avoid a rollback round trip."""
        connection = self._raw_connection()
        connection.autocommit = True
        return connection

    def _collection_uuid(self, collection_name: str) -> Optional[str]:
        """Resolve and cache a collection UUID to remove a lookup from hot searches."""
        cached = self._collection_uuid_cache.get(collection_name)
        if cached is not None:
            return cached
        connection = self._read_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT uuid FROM langchain_pg_collection WHERE name = %s;",
                    (collection_name,),
                )
                row = cursor.fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        # The canonical UUID representation is also safe to embed in a query
        # predicate when selecting a collection-local partial index.
        resolved = str(UUID(str(row[0])))
        with self._collection_uuid_lock:
            self._collection_uuid_cache[collection_name] = resolved
        return resolved

    async def _collection_uuid_async(self, collection_name: str) -> Optional[str]:
        """Resolve collection identity without blocking the workflow event loop."""
        cached = self._collection_uuid_cache.get(collection_name)
        if cached is not None:
            return cached
        raw_url = getattr(self, "database_url", PGVECTOR_URL).replace(
            "postgresql+psycopg://",
            "postgresql://",
        )
        async with get_pooled_async_connection(raw_url) as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT uuid FROM langchain_pg_collection WHERE name = %s;",
                    (collection_name,),
                )
                row = await cursor.fetchone()
        if row is None:
            return None
        resolved = str(UUID(str(row[0])))
        with self._collection_uuid_lock:
            self._collection_uuid_cache[collection_name] = resolved
        return resolved

    def _create_collection(
        self,
        collection_name: str,
        metadata: Dict[str, Any],
    ) -> str:
        collection_uuid = str(uuid4())
        connection = self._raw_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO langchain_pg_collection (uuid, name, cmetadata)
                    VALUES (%s, %s, %s)
                    RETURNING uuid;
                    """,
                    (
                        collection_uuid,
                        collection_name,
                        psycopg2.extras.Json(metadata),
                    ),
                )
                row = cursor.fetchone()
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        if row is None:
            raise PgVectorStoreError(
                f"pgvector 컬렉션 생성 결과가 비어 있습니다: {collection_name}"
            )
        resolved = str(UUID(str(row[0])))
        with self._collection_uuid_lock:
            self._collection_uuid_cache[collection_name] = resolved
        return resolved

    def _delete_collection(self, collection_name: str) -> None:
        connection = self._raw_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM langchain_pg_collection WHERE name = %s;",
                    (collection_name,),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        with self._collection_uuid_lock:
            self._collection_uuid_cache.pop(collection_name, None)

    @staticmethod
    def _collection_metadata(
        metadata: Optional[Dict[str, Any]],
        *,
        model_name: str,
        document_count: int,
    ) -> Dict[str, Any]:
        meta_dict = metadata or {}
        return {
            "file_name": meta_dict.get("file_name", ""),
            "workbook_hash": meta_dict.get("workbook_hash", ""),
            "model": meta_dict.get("model", model_name),
            "dimension": meta_dict.get("dimension", DEFAULT_EMBEDDING_DIMENSION),
            "document_count": document_count,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "pipeline": meta_dict.get("pipeline", "luna_vlm_structured"),
            "duration_seconds": meta_dict.get("duration_seconds"),
            "total_tokens": meta_dict.get("total_tokens"),
            "estimated_cost_usd": meta_dict.get("estimated_cost_usd"),
            "estimated_cost_krw": meta_dict.get("estimated_cost_krw"),
            "batch_size": meta_dict.get("batch_size"),
            "company_name": meta_dict.get("company_name", ""),
            "ticker": meta_dict.get("ticker", ""),
            "operation_id": meta_dict.get("operation_id"),
        }

    def prepare_collection_replace(
        self,
        *,
        index_id: str,
        operation_id: str,
        model_name: str,
        document_count: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PgVectorReplacePlan:
        """Return a retry-stable private collection for distributed shard COPY."""

        clean_meta = self._collection_metadata(
            {**(metadata or {}), "operation_id": operation_id},
            model_name=model_name,
            document_count=document_count,
        )
        dimension = int(clean_meta["dimension"])
        published_uuid = self._collection_uuid(index_id)
        if (
            published_uuid is not None
            and self.collection_document_count(published_uuid) == document_count
        ):
            return PgVectorReplacePlan(
                index_id=index_id,
                operation_id=operation_id,
                staging_name=index_id,
                staging_uuid=published_uuid,
                dimension=dimension,
                metadata=clean_meta,
                published=True,
            )

        staging_name = f"{index_id}__staging__{operation_id[:16]}"
        staging_uuid = self._collection_uuid(staging_name)
        if staging_uuid is None:
            try:
                staging_uuid = self._create_collection(staging_name, clean_meta)
            except Exception:
                # A concurrent coordinator for the same content may have won
                # the unique-name race. Reuse that deterministic staging row.
                staging_uuid = self._collection_uuid(staging_name)
                if staging_uuid is None:
                    raise
        return PgVectorReplacePlan(
            index_id=index_id,
            operation_id=operation_id,
            staging_name=staging_name,
            staging_uuid=staging_uuid,
            dimension=dimension,
            metadata=clean_meta,
        )

    def copy_prepared_collection_shard(
        self,
        plan: PgVectorReplacePlan,
        *,
        documents: Sequence[Document],
        vectors: Sequence[Sequence[float]],
        start_index: int,
    ) -> None:
        """Idempotently replace one disjoint row range in a private collection."""

        if plan.published:
            return
        if len(documents) != len(vectors):
            raise PgVectorStoreError("pgvector shard 문서와 벡터 개수가 다릅니다")
        document_ids = [
            str(uuid5(UUID(plan.staging_uuid), str(start_index + offset)))
            for offset in range(len(documents))
        ]
        connection = self._raw_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM langchain_pg_embedding WHERE id = ANY(%s::varchar[]);",
                    (document_ids,),
                )
            copy_documents(
                connection,
                collection_uuid=plan.staging_uuid,
                documents=documents,
                vectors=vectors,
                batch_size=max(1, len(documents)),
                document_ids=document_ids,
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def collection_document_count(self, collection_uuid: str) -> int:
        connection = self._read_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM langchain_pg_embedding WHERE collection_id = %s;",
                    (collection_uuid,),
                )
                row = cursor.fetchone()
        finally:
            connection.close()
        return int(row[0]) if row else 0

    def publish_prepared_collection(self, plan: PgVectorReplacePlan) -> None:
        """Build one HNSW index and atomically expose a fully copied collection."""

        if plan.published:
            return
        actual_count = self.collection_document_count(plan.staging_uuid)
        expected_count = int(plan.metadata["document_count"])
        if actual_count != expected_count:
            raise PgVectorStoreError(
                "pgvector staging collection 문서 수가 일치하지 않습니다 "
                f"({actual_count}/{expected_count})"
            )
        self.ensure_collection_vector_index(plan.staging_name, plan.dimension)

        retired_name = f"{plan.index_id}__retired__{uuid4().hex}"
        retired_uuid: Optional[str] = None
        retired_dimension = plan.dimension
        connection = self._raw_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s));",
                    (plan.index_id,),
                )
                cursor.execute(
                    """
                    UPDATE langchain_pg_collection
                    SET name = %s
                    WHERE name = %s
                    RETURNING uuid, cmetadata;
                    """,
                    (retired_name, plan.index_id),
                )
                retired = cursor.fetchone()
                if retired is not None:
                    retired_uuid = str(retired[0])
                    if isinstance(retired[1], dict):
                        retired_dimension = int(retired[1].get("dimension") or retired_dimension)
                cursor.execute(
                    """
                    UPDATE langchain_pg_collection
                    SET name = %s, cmetadata = %s
                    WHERE name = %s
                    RETURNING uuid;
                    """,
                    (
                        plan.index_id,
                        psycopg2.extras.Json(plan.metadata),
                        plan.staging_name,
                    ),
                )
                published = cursor.fetchone()
                if published is None:
                    # Another retry may have published the same deterministic
                    # staging collection while this coordinator was waiting.
                    cursor.execute(
                        "SELECT uuid FROM langchain_pg_collection WHERE name = %s;",
                        (plan.index_id,),
                    )
                    published = cursor.fetchone()
                if published is None:
                    raise PgVectorStoreError("완료된 pgvector staging collection이 없습니다")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        published_uuid = str(UUID(str(published[0])))
        with self._collection_uuid_lock:
            self._collection_uuid_cache.pop(plan.staging_name, None)
            self._collection_uuid_cache[plan.index_id] = published_uuid

        if retired_uuid is not None and retired_uuid != published_uuid:
            try:
                self._delete_collection(retired_name)
                self._drop_collection_vector_index(retired_uuid, retired_dimension)
            except Exception:
                logger.warning(
                    "교체된 pgvector collection 정리 실패: %s",
                    retired_name,
                    exc_info=True,
                )
        self.ensure_optimized_indexes()

    @staticmethod
    def _collection_vector_index_name(collection_uuid: str, dimension: int) -> str:
        uuid_hex = UUID(collection_uuid).hex
        return f"idx_lc_hnsw_bq_c_{uuid_hex}_{dimension}"

    def ensure_collection_vector_index(
        self,
        collection_name: str,
        dimension: int,
    ) -> str:
        """Create a compact collection-local binary-quantized HNSW index."""
        collection_uuid = self._collection_uuid(collection_name)
        if collection_uuid is None:
            raise PgVectorStoreError(f"컬렉션별 HNSW 인덱스 대상이 없습니다: {collection_name}")
        if not 0 < dimension <= 64_000:
            raise PgVectorStoreError(f"HNSW 인덱스를 지원하지 않는 벡터 차원입니다: {dimension}")
        index_name = self._collection_vector_index_name(collection_uuid, dimension)
        connection = self._read_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    CREATE INDEX CONCURRENTLY IF NOT EXISTS "{index_name}"
                    ON langchain_pg_embedding
                    USING hnsw (
                        (binary_quantize(embedding)::bit({dimension}))
                        bit_hamming_ops
                    )
                    WHERE collection_id = '{collection_uuid}'::uuid
                      AND vector_dims(embedding) = {dimension};
                    """
                )
        finally:
            connection.close()
        return index_name

    def _drop_collection_vector_index(
        self,
        collection_uuid: str,
        dimension: int,
    ) -> None:
        index_name = self._collection_vector_index_name(collection_uuid, dimension)
        connection = self._read_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f'DROP INDEX CONCURRENTLY IF EXISTS "{index_name}";')
        finally:
            connection.close()

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

    def put_documents(
        self,
        index_id: str,
        documents: Sequence[Document],
        model_name: str = DEFAULT_EMBEDDING_MODEL,
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
            "dimension": meta_dict.get("dimension", DEFAULT_EMBEDDING_DIMENSION),
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
            if isinstance(vectors, EmbeddingArtifactVectors) and vectors.dimension != int(
                clean_meta["dimension"]
            ):
                raise PgVectorStoreError(
                    "float32 아티팩트 차원과 컬렉션 메타데이터 차원이 일치하지 않습니다"
                )

        swap_suffix = uuid4().hex
        staging_name = f"{index_id}__staging__{swap_suffix}"
        retired_name = f"{index_id}__retired__{swap_suffix}"
        # Build a private staging collection so the current queryable index
        # remains intact until every batch has been persisted successfully.
        try:
            staging_uuid = self._create_collection(staging_name, clean_meta)
        except Exception as create_error:
            logger.error(
                "pgvector 컬렉션('%s') 생성 실패: %s",
                staging_name,
                create_error,
                exc_info=True,
            )
            raise PgVectorStoreError(
                f"pgvector 스테이징 컬렉션('{staging_name}') 생성 실패: {create_error}"
            ) from create_error

        total_batches = max(
            1,
            (total_items + PGVECTOR_INSERT_BATCH_SIZE - 1) // PGVECTOR_INSERT_BATCH_SIZE,
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
        batch_index = 0
        copy_connection = self._raw_connection()
        try:
            if isinstance(vectors, EmbeddingArtifactVectors):
                copy_documents(
                    copy_connection,
                    collection_uuid=staging_uuid,
                    documents=documents,
                    vectors=vectors,
                    batch_size=PGVECTOR_INSERT_BATCH_SIZE,
                    progress_callback=progress_callback,
                )
                batch_index = total_batches
            else:
                if embedding_encoder is None:
                    raise PgVectorStoreError(
                        "동적 문서 임베딩에는 embedding_encoder 주입이 필요합니다"
                    )
                for batch_index, start in enumerate(
                    range(0, total_items, PGVECTOR_INSERT_BATCH_SIZE),
                    start=1,
                ):
                    stop = min(start + PGVECTOR_INSERT_BATCH_SIZE, total_items)
                    document_batch = list(documents[start:stop])
                    if use_precomputed_vectors and vectors is not None:
                        vector_batch = [
                            [float(value) for value in vector] for vector in vectors[start:stop]
                        ]
                    else:
                        vector_batch = embedding_encoder.encode(
                            [document.page_content for document in document_batch]
                        )
                    copy_documents(
                        copy_connection,
                        collection_uuid=staging_uuid,
                        documents=document_batch,
                        vectors=vector_batch,
                        batch_size=PGVECTOR_INSERT_BATCH_SIZE,
                    )
                    if progress_callback is not None:
                        progress_callback(
                            {
                                "completed_batches": batch_index,
                                "total_batches": total_batches,
                                "completed_items": stop,
                                "total_items": total_items,
                            }
                        )
            copy_connection.commit()
        except Exception as error:
            copy_connection.rollback()
            # A failed write must not leave a queryable partial collection.
            try:
                self._delete_collection(staging_name)
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
        finally:
            copy_connection.close()

        try:
            self.ensure_collection_vector_index(
                staging_name,
                int(clean_meta["dimension"]),
            )
        except Exception as index_error:
            staging_uuid = self._collection_uuid_cache.get(staging_name)
            try:
                self._delete_collection(staging_name)
            except Exception:
                pass
            if staging_uuid is not None:
                try:
                    self._drop_collection_vector_index(
                        staging_uuid,
                        int(clean_meta["dimension"]),
                    )
                except Exception:
                    pass
            raise PgVectorStoreError(
                f"컬렉션별 HNSW 인덱스 생성 실패: {index_error}"
            ) from index_error

        # Atomically publish the completed staging collection. Renaming the old
        # collection first keeps reads available and makes a failed rebuild
        # non-destructive.
        had_previous_collection = False
        retired_uuid: Optional[str] = None
        retired_dimension = int(clean_meta["dimension"])
        published_uuid: Optional[str] = None
        try:
            conn = self._raw_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT pg_advisory_xact_lock(hashtext(%s));
                        """,
                        (index_id,),
                    )
                    cur.execute(
                        """
                        UPDATE langchain_pg_collection
                        SET name = %s
                        WHERE name = %s
                        RETURNING uuid, cmetadata;
                        """,
                        (retired_name, index_id),
                    )
                    retired_row = cur.fetchone()
                    had_previous_collection = retired_row is not None
                    if retired_row is not None:
                        retired_uuid = str(retired_row[0])
                        retired_metadata = retired_row[1]
                        if isinstance(retired_metadata, dict):
                            retired_dimension = int(
                                retired_metadata.get("dimension") or retired_dimension
                            )
                    cur.execute(
                        """
                        UPDATE langchain_pg_collection
                        SET name = %s, cmetadata = %s
                        WHERE name = %s
                        RETURNING uuid;
                        """,
                        (
                            index_id,
                            psycopg2.extras.Json(clean_meta),
                            staging_name,
                        ),
                    )
                    published_row = cur.fetchone()
                    if published_row is None:
                        raise PgVectorStoreError(
                            "완료된 pgvector 스테이징 컬렉션을 찾을 수 없습니다"
                        )
                    published_uuid = str(published_row[0])
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
        except Exception as publish_error:
            staging_uuid = self._collection_uuid_cache.get(staging_name)
            try:
                self._delete_collection(staging_name)
            except Exception:
                pass
            if staging_uuid is not None:
                try:
                    self._drop_collection_vector_index(
                        staging_uuid,
                        int(clean_meta["dimension"]),
                    )
                except Exception:
                    pass
            raise PgVectorStoreError(
                f"pgvector 컬렉션 원자적 교체 실패: {publish_error}"
            ) from publish_error

        if published_uuid is not None:
            with self._collection_uuid_lock:
                self._collection_uuid_cache.pop(staging_name, None)
                self._collection_uuid_cache[index_id] = published_uuid

        if had_previous_collection:
            try:
                cleanup_conn = self._raw_connection()
                try:
                    with cleanup_conn.cursor() as cur:
                        cur.execute(
                            "DELETE FROM langchain_pg_collection WHERE name = %s;",
                            (retired_name,),
                        )
                    cleanup_conn.commit()
                finally:
                    cleanup_conn.close()
                if retired_uuid is not None:
                    self._drop_collection_vector_index(
                        retired_uuid,
                        retired_dimension,
                    )
            except Exception:
                logger.warning(
                    "교체된 이전 pgvector 컬렉션 정리 실패: %s",
                    retired_name,
                    exc_info=True,
                )

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
        model_name = meta_dict.get("model", DEFAULT_EMBEDDING_MODEL)
        file_name = meta_dict.get("file_name", "")
        workbook_hash = meta_dict.get("workbook_hash", "")
        company_name = meta_dict.get("company_name", "")

        resolved_vectors = vectors if vectors is not None else vectors_or_items
        usable_vectors = (
            resolved_vectors if _is_numeric_vector_collection(resolved_vectors) else None
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
                    SELECT c.name, c.cmetadata, COALESCE(e.chunk_count, 0) AS chunk_count
                    FROM langchain_pg_collection c
                    LEFT JOIN (
                        SELECT collection_id, COUNT(*) AS chunk_count
                        FROM langchain_pg_embedding
                        GROUP BY collection_id
                    ) e ON c.uuid = e.collection_id;
                    """
                )
                rows = cur.fetchall()
        finally:
            conn.close()

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
            cmeta = c[1] or {}
            if isinstance(cmeta, str):
                import json

                try:
                    cmeta = json.loads(cmeta)
                except Exception:
                    cmeta = {}
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
