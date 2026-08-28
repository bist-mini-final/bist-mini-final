"""Canonical bounded-memory PostgreSQL binary COPY stream for pgvector rows."""

from __future__ import annotations

import io
import json
import struct
import sys
from array import array
from collections import deque
from typing import Any, Callable, Deque, Dict, Iterator, Optional, Sequence
from uuid import UUID, uuid4

from langchain_core.documents import Document

from backend.storage.embedding_artifacts import EmbeddingArtifactVectors
from modules.common.base_module import ModuleExecutionError

_COPY_HEADER = b"PGCOPY\n\xff\r\n\x00" + struct.pack("!II", 0, 0)
_COPY_TRAILER = struct.pack("!h", -1)
_COPY_FIELD_COUNT = 5
_DEFAULT_READ_SIZE = 1024 * 1024


def _field_prefix(length: int) -> bytes:
    return struct.pack("!i", length)


class PgVectorBinaryCopyStream(io.RawIOBase):
    """Pull-based COPY stream for artifact-backed or ordinary float vectors.

    Artifact vectors are stored as little-endian float32. PostgreSQL's binary
    protocol expects network byte order, so each bounded raw batch is byte-swapped
    once with a C-backed ``array`` operation. Row framing is emitted as small
    memoryview segments and consumed by psycopg without constructing a full COPY
    payload in memory. Ordinary vector sequences use the same row framing and are
    converted in bounded batches, keeping Binary COPY as the sole embedding write
    path.
    """

    def __init__(
        self,
        documents: Sequence[Document],
        vectors: EmbeddingArtifactVectors | Sequence[Sequence[float]],
        collection_uuid: str,
        *,
        batch_size: int,
        progress_callback: Optional[Callable[[Dict[str, int]], None]] = None,
    ) -> None:
        super().__init__()
        if len(documents) != len(vectors):
            raise ModuleExecutionError(
                "COPY 대상 문서 개수와 float32 벡터 개수가 일치하지 않습니다"
            )
        dimension = (
            vectors.dimension
            if isinstance(vectors, EmbeddingArtifactVectors)
            else len(vectors[0])
        )
        if not 0 < dimension <= 32_767:
            raise ModuleExecutionError(
                f"PostgreSQL vector 바이너리 차원이 올바르지 않습니다: {dimension}"
            )
        self._documents = documents
        self._vectors = vectors
        self._collection_uuid = UUID(collection_uuid).bytes
        self._batch_size = max(1, batch_size)
        self._progress_callback = progress_callback
        self._raw_batches: Iterator[bytes] | None = (
            vectors.iter_raw_batches(self._batch_size)
            if isinstance(vectors, EmbeddingArtifactVectors)
            else None
        )
        self._sequence_batch_start = 0
        self._segments: Deque[memoryview] = deque([memoryview(_COPY_HEADER)])
        self._document_index = 0
        self._current_batch: Optional[memoryview] = None
        self._current_batch_position = 0
        self._current_batch_count = 0
        self._trailer_queued = False
        self._dimension = dimension
        self._bytes_per_vector = dimension * 4
        self._vector_field_header = struct.pack("!HH", dimension, 0)
        self._total_batches = max(
            1,
            (len(documents) + self._batch_size - 1) // self._batch_size,
        )

    @property
    def rows_emitted(self) -> int:
        """Return how many complete rows have been framed for COPY."""
        return self._document_index

    def readable(self) -> bool:
        return True

    def _load_vector_batch(self) -> None:
        if isinstance(self._vectors, EmbeddingArtifactVectors):
            assert self._raw_batches is not None
            try:
                raw = next(self._raw_batches)
            except StopIteration as error:
                raise ModuleExecutionError(
                    "float32 아티팩트가 문서 개수보다 먼저 종료되었습니다"
                ) from error
            if len(raw) % self._bytes_per_vector != 0:
                raise ModuleExecutionError(
                    "float32 아티팩트 배치가 벡터 경계에 맞지 않습니다"
                )
            vector_count = len(raw) // self._bytes_per_vector
            words = array("I")
            if words.itemsize != 4:
                raise ModuleExecutionError(
                    "현재 플랫폼의 32비트 word 크기가 PostgreSQL COPY 형식과 다릅니다"
                )
            words.frombytes(raw)
            # Artifact bytes are little-endian and PostgreSQL binary values use
            # network byte order. Swapping the raw words avoids float objects.
            if sys.byteorder == "little":
                words.byteswap()
        else:
            stop = min(
                self._sequence_batch_start + self._batch_size,
                len(self._vectors),
            )
            if stop <= self._sequence_batch_start:
                raise ModuleExecutionError(
                    "벡터 시퀀스가 문서 개수보다 먼저 종료되었습니다"
                )
            words = array("f")
            for vector in self._vectors[self._sequence_batch_start:stop]:
                if len(vector) != self._dimension:
                    raise ModuleExecutionError(
                        "COPY 벡터 차원이 컬렉션 메타데이터와 일치하지 않습니다"
                    )
                try:
                    words.extend(float(value) for value in vector)
                except (TypeError, ValueError, OverflowError) as error:
                    raise ModuleExecutionError(
                        "COPY 벡터에 float32로 변환할 수 없는 값이 있습니다"
                    ) from error
            if words.itemsize != 4:
                raise ModuleExecutionError(
                    "현재 플랫폼의 float32 word 크기가 PostgreSQL COPY 형식과 다릅니다"
                )
            if sys.byteorder == "little":
                words.byteswap()
            vector_count = stop - self._sequence_batch_start
            self._sequence_batch_start = stop
        self._current_batch = memoryview(words).cast("B")
        self._current_batch_position = 0
        self._current_batch_count = vector_count

    def _next_vector(self) -> memoryview:
        if (
            self._current_batch is None
            or self._current_batch_position >= self._current_batch_count
        ):
            self._load_vector_batch()
        assert self._current_batch is not None
        start = self._current_batch_position * self._bytes_per_vector
        stop = start + self._bytes_per_vector
        self._current_batch_position += 1
        return self._current_batch[start:stop]

    def _queue_row(self) -> None:
        if self._document_index >= len(self._documents):
            if not self._trailer_queued:
                self._segments.append(memoryview(_COPY_TRAILER))
                self._trailer_queued = True
            return

        document = self._documents[self._document_index]
        vector_bytes = self._next_vector()
        # The embedding table primary key is global, not scoped by collection.
        # A staging rebuild therefore needs fresh row IDs even when the logical
        # Document IDs match rows in the currently published collection.
        document_id = str(uuid4()).encode("utf-8")
        document_text = document.page_content.encode("utf-8")
        metadata_json = json.dumps(
            document.metadata or {},
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        jsonb = b"\x01" + metadata_json

        row_prefix = b"".join(
            (
                struct.pack("!h", _COPY_FIELD_COUNT),
                _field_prefix(len(document_id)),
                document_id,
                _field_prefix(len(self._collection_uuid)),
                self._collection_uuid,
                _field_prefix(len(self._vector_field_header) + len(vector_bytes)),
                self._vector_field_header,
            )
        )
        self._segments.extend(
            (
                memoryview(row_prefix),
                vector_bytes,
                memoryview(_field_prefix(len(document_text))),
                memoryview(document_text),
                memoryview(_field_prefix(len(jsonb))),
                memoryview(jsonb),
            )
        )
        self._document_index += 1

        if (
            self._progress_callback is not None
            and (
                self._document_index % self._batch_size == 0
                or self._document_index == len(self._documents)
            )
        ):
            completed_batches = min(
                self._total_batches,
                (self._document_index + self._batch_size - 1) // self._batch_size,
            )
            self._progress_callback(
                {
                    "completed_batches": completed_batches,
                    "total_batches": self._total_batches,
                    "completed_items": self._document_index,
                    "total_items": len(self._documents),
                }
            )

    def _read_bounded(self, size: int) -> bytes:
        output = bytearray()
        while len(output) < size:
            if not self._segments:
                if self._trailer_queued:
                    break
                self._queue_row()
                if not self._segments:
                    break
            segment = self._segments[0]
            remaining = size - len(output)
            take = min(remaining, len(segment))
            output.extend(segment[:take])
            if take == len(segment):
                self._segments.popleft()
            else:
                self._segments[0] = segment[take:]
        return bytes(output)

    def read(self, size: int = -1) -> bytes:
        if self.closed:
            return b""
        if size is None or size < 0:
            chunks = []
            while chunk := self._read_bounded(_DEFAULT_READ_SIZE):
                chunks.append(chunk)
            return b"".join(chunks)
        if size == 0:
            return b""
        return self._read_bounded(size)

    def close(self) -> None:
        close_batches = getattr(self._raw_batches, "close", None)
        if callable(close_batches):
            close_batches()
        self._segments.clear()
        self._current_batch = None
        super().close()


def copy_documents(
    connection: Any,
    *,
    collection_uuid: str,
    documents: Sequence[Document],
    vectors: EmbeddingArtifactVectors | Sequence[Sequence[float]],
    batch_size: int,
    progress_callback: Optional[Callable[[Dict[str, int]], None]] = None,
) -> None:
    """Stream documents and vectors into an empty collection using Binary COPY."""
    stream = PgVectorBinaryCopyStream(
        documents,
        vectors,
        collection_uuid,
        batch_size=batch_size,
        progress_callback=progress_callback,
    )
    try:
        with connection.cursor() as cursor:
            cursor.copy_expert(
                """
                COPY langchain_pg_embedding
                    (id, collection_id, embedding, document, cmetadata)
                FROM STDIN WITH (FORMAT BINARY)
                """,
                stream,
                size=_DEFAULT_READ_SIZE,
            )
    finally:
        stream.close()


__all__ = [
    "PgVectorBinaryCopyStream",
    "copy_documents",
]
