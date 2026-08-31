"""Collection staging, binary COPY, and atomic pgvector publication."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from numbers import Real
from typing import Any, Callable, Dict, Optional, Sequence
from uuid import UUID, uuid4, uuid5

import psycopg2.extras
from langchain_core.documents import Document

from backend.domains.data_sources.infrastructure.filesystem.embedding_artifacts import (
    EmbeddingArtifactVectors,
)
from backend.domains.data_sources.infrastructure.spreadsheets.langchain_document import (
    cell_items_to_langchain_documents,
)
from backend.shared.application.embeddings import EmbeddingEncoder
from backend.shared.application.vector import PgVectorReplacePlan
from backend.storage.pgvector_binary_copy import copy_documents
from backend.storage.pgvector_errors import PgVectorStoreError
from modules.common.config import DEFAULT_EMBEDDING_DIMENSION, DEFAULT_EMBEDDING_MODEL

from .base import PgVectorConnectionCapability

logger = logging.getLogger(__name__)

PGVECTOR_INSERT_BATCH_SIZE = 1000


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


class PgVectorWriteMixin(PgVectorConnectionCapability):
    """Write-side collection lifecycle and atomic publication capability."""

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

    @staticmethod
    def _validate_document_vectors(
        documents: Sequence[Document],
        vectors: Optional[Any],
        dimension: int,
    ) -> bool:
        if vectors is None:
            return False
        if len(vectors) != len(documents):
            raise PgVectorStoreError(
                f"사전 계산된 벡터 개수({len(vectors)})가 문서 개수({len(documents)})와 일치하지 않습니다."
            )
        if isinstance(vectors, EmbeddingArtifactVectors) and vectors.dimension != dimension:
            raise PgVectorStoreError(
                "float32 아티팩트 차원과 컬렉션 메타데이터 차원이 일치하지 않습니다"
            )
        return True

    def _create_staging_collection(
        self,
        staging_name: str,
        metadata: Dict[str, Any],
    ) -> str:
        try:
            return self._create_collection(staging_name, metadata)
        except Exception as error:
            logger.error(
                "pgvector 컬렉션('%s') 생성 실패: %s",
                staging_name,
                error,
                exc_info=True,
            )
            raise PgVectorStoreError(
                f"pgvector 스테이징 컬렉션('{staging_name}') 생성 실패: {error}"
            ) from error

    def _cleanup_staging_collection(self, staging_name: str, dimension: int) -> None:
        staging_uuid = self._collection_uuid_cache.get(staging_name)
        try:
            self._delete_collection(staging_name)
        except Exception:
            pass
        if staging_uuid is not None and dimension > 0:
            try:
                self._drop_collection_vector_index(staging_uuid, dimension)
            except Exception:
                pass

    @staticmethod
    def _copy_progress(
        callback: Optional[Callable[[Dict[str, int]], None]],
        *,
        completed_batches: int,
        total_batches: int,
        completed_items: int,
        total_items: int,
    ) -> None:
        if callback is not None:
            callback(
                {
                    "completed_batches": completed_batches,
                    "total_batches": total_batches,
                    "completed_items": completed_items,
                    "total_items": total_items,
                }
            )

    def _copy_staging_documents(
        self,
        *,
        staging_name: str,
        staging_uuid: str,
        documents: Sequence[Document],
        vectors: Optional[Any],
        embedding_encoder: Optional[EmbeddingEncoder],
        use_precomputed_vectors: bool,
        progress_callback: Optional[Callable[[Dict[str, int]], None]],
    ) -> None:
        total_items = len(documents)
        total_batches = max(
            1,
            (total_items + PGVECTOR_INSERT_BATCH_SIZE - 1) // PGVECTOR_INSERT_BATCH_SIZE,
        )
        self._copy_progress(
            progress_callback,
            completed_batches=0,
            total_batches=total_batches,
            completed_items=0,
            total_items=total_items,
        )
        batch_index = 0
        connection = self._raw_connection()
        try:
            if isinstance(vectors, EmbeddingArtifactVectors):
                copy_documents(
                    connection,
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
                    vector_batch = (
                        [[float(value) for value in vector] for vector in vectors[start:stop]]
                        if use_precomputed_vectors and vectors is not None
                        else embedding_encoder.encode(
                            [document.page_content for document in document_batch]
                        )
                    )
                    copy_documents(
                        connection,
                        collection_uuid=staging_uuid,
                        documents=document_batch,
                        vectors=vector_batch,
                        batch_size=PGVECTOR_INSERT_BATCH_SIZE,
                    )
                    self._copy_progress(
                        progress_callback,
                        completed_batches=batch_index,
                        total_batches=total_batches,
                        completed_items=stop,
                        total_items=total_items,
                    )
            connection.commit()
        except Exception as error:
            connection.rollback()
            self._cleanup_staging_collection(staging_name, 0)
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
            connection.close()

    def _ensure_staging_vector_index(
        self,
        staging_name: str,
        dimension: int,
    ) -> None:
        try:
            self.ensure_collection_vector_index(staging_name, dimension)
        except Exception as error:
            self._cleanup_staging_collection(staging_name, dimension)
            raise PgVectorStoreError(f"컬렉션별 HNSW 인덱스 생성 실패: {error}") from error

    def _publish_staging_collection(
        self,
        *,
        index_id: str,
        staging_name: str,
        retired_name: str,
        metadata: Dict[str, Any],
    ) -> tuple[Optional[str], int, str]:
        retired_uuid: Optional[str] = None
        retired_dimension = int(metadata["dimension"])
        connection = self._raw_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s));", (index_id,))
                cursor.execute(
                    """
                    UPDATE langchain_pg_collection
                    SET name = %s
                    WHERE name = %s
                    RETURNING uuid, cmetadata;
                    """,
                    (retired_name, index_id),
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
                    (index_id, psycopg2.extras.Json(metadata), staging_name),
                )
                published = cursor.fetchone()
                if published is None:
                    raise PgVectorStoreError("완료된 pgvector 스테이징 컬렉션을 찾을 수 없습니다")
            connection.commit()
            return retired_uuid, retired_dimension, str(published[0])
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _cleanup_retired_collection(
        self,
        retired_name: str,
        retired_uuid: Optional[str],
        retired_dimension: int,
    ) -> None:
        if retired_uuid is None:
            return
        try:
            self._delete_collection(retired_name)
            self._drop_collection_vector_index(retired_uuid, retired_dimension)
        except Exception:
            logger.warning(
                "교체된 이전 pgvector 컬렉션 정리 실패: %s",
                retired_name,
                exc_info=True,
            )

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
        """Atomically replace one collection with a fully persisted document set."""
        if not documents:
            return
        clean_meta = self._collection_metadata(
            metadata,
            model_name=model_name,
            document_count=len(documents),
        )
        clean_meta.pop("operation_id", None)
        dimension = int(clean_meta["dimension"])
        use_precomputed_vectors = self._validate_document_vectors(
            documents,
            vectors,
            dimension,
        )
        suffix = uuid4().hex
        staging_name = f"{index_id}__staging__{suffix}"
        retired_name = f"{index_id}__retired__{suffix}"
        staging_uuid = self._create_staging_collection(staging_name, clean_meta)
        self._copy_staging_documents(
            staging_name=staging_name,
            staging_uuid=staging_uuid,
            documents=documents,
            vectors=vectors,
            embedding_encoder=embedding_encoder,
            use_precomputed_vectors=use_precomputed_vectors,
            progress_callback=progress_callback,
        )
        self._ensure_staging_vector_index(staging_name, dimension)
        try:
            retired_uuid, retired_dimension, published_uuid = self._publish_staging_collection(
                index_id=index_id,
                staging_name=staging_name,
                retired_name=retired_name,
                metadata=clean_meta,
            )
        except Exception as error:
            self._cleanup_staging_collection(staging_name, dimension)
            raise PgVectorStoreError(f"pgvector 컬렉션 원자적 교체 실패: {error}") from error
        with self._collection_uuid_lock:
            self._collection_uuid_cache.pop(staging_name, None)
            self._collection_uuid_cache[index_id] = published_uuid
        self._cleanup_retired_collection(
            retired_name,
            retired_uuid,
            retired_dimension,
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


__all__ = ["PGVECTOR_INSERT_BATCH_SIZE", "PgVectorWriteMixin"]
