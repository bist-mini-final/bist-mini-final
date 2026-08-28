from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from langchain_core.documents import Document

from backend.storage.embedding_artifacts import (
    EmbeddingArtifactStore,
    EmbeddingArtifactVectors,
)
from backend.storage.pgvector_binary_copy import PgVectorBinaryCopyStream
from backend.storage.pgvector_store import PgVectorStore, PgVectorStoreError


def test_binary_copy_stream_avoids_python_vector_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_store = EmbeddingArtifactStore(tmp_path)
    artifact_id = "c" * 64
    artifact_store.put(artifact_id, [[0.25, -0.5], [1.0, 0.125]])
    vectors = artifact_store.vector_sequence(artifact_id, 2, 2)

    def _forbid_vector_indexing(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("binary COPY must not create Python vector lists")

    monkeypatch.setattr(EmbeddingArtifactVectors, "__getitem__", _forbid_vector_indexing)
    progress: list[dict[str, int]] = []
    stream = PgVectorBinaryCopyStream(
        [
            Document(page_content="first", metadata={"cell_id": "A1"}, id="id-1"),
            Document(page_content="second", metadata={"cell_id": "A2"}, id="id-2"),
        ],
        vectors,
        "11111111-1111-1111-1111-111111111111",
        batch_size=1,
        progress_callback=progress.append,
    )
    payload = b"".join(iter(lambda: stream.read(7), b""))
    stream.close()

    offset = len(b"PGCOPY\n\xff\r\n\x00") + 8
    emitted_ids: list[str] = []
    decoded_vectors: list[tuple[float, float]] = []
    decoded_metadata: list[dict[str, Any]] = []
    for _ in range(2):
        field_count = struct.unpack_from("!h", payload, offset)[0]
        offset += 2
        assert field_count == 5
        fields = []
        for _field in range(field_count):
            field_length = struct.unpack_from("!i", payload, offset)[0]
            offset += 4
            fields.append(payload[offset : offset + field_length])
            offset += field_length
        emitted_ids.append(fields[0].decode("utf-8"))
        dimension, reserved = struct.unpack_from("!HH", fields[2], 0)
        assert (dimension, reserved) == (2, 0)
        decoded_vectors.append(struct.unpack_from("!2f", fields[2], 4))
        assert fields[4][0] == 1
        decoded_metadata.append(json.loads(fields[4][1:]))

    assert struct.unpack_from("!h", payload, offset)[0] == -1
    assert len(set(emitted_ids)) == 2
    assert set(emitted_ids).isdisjoint({"id-1", "id-2"})
    assert decoded_vectors == pytest.approx([(0.25, -0.5), (1.0, 0.125)])
    assert decoded_metadata == [{"cell_id": "A1"}, {"cell_id": "A2"}]
    assert progress[-1]["completed_items"] == 2


def test_float32_raw_batches_use_one_contiguous_file_reader(tmp_path: Path) -> None:
    artifact_store = EmbeddingArtifactStore(tmp_path)
    artifact_id = "d" * 64
    artifact_store.put(
        artifact_id,
        [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]],
    )

    batches = list(artifact_store.iter_raw_batches(artifact_id, 3, 2, batch_size=2))

    assert [len(batch) for batch in batches] == [16, 8]
    assert struct.unpack("<4f", batches[0]) == pytest.approx((0.1, 0.2, 0.3, 0.4))
    assert struct.unpack("<2f", batches[1]) == pytest.approx((0.5, 0.6))


def test_binary_copy_stream_supports_ordinary_vector_sequences() -> None:
    stream = PgVectorBinaryCopyStream(
        [
            Document(page_content="first", metadata={}),
            Document(page_content="second", metadata={}),
        ],
        [[0.25, -0.5], [1.0, 0.125]],
        "11111111-1111-1111-1111-111111111111",
        batch_size=1,
    )
    payload = b"".join(iter(lambda: stream.read(11), b""))
    stream.close()

    offset = len(b"PGCOPY\n\xff\r\n\x00") + 8
    decoded_vectors: list[tuple[float, float]] = []
    for _ in range(2):
        field_count = struct.unpack_from("!h", payload, offset)[0]
        offset += 2
        fields = []
        for _field in range(field_count):
            field_length = struct.unpack_from("!i", payload, offset)[0]
            offset += 4
            fields.append(payload[offset : offset + field_length])
            offset += field_length
        decoded_vectors.append(struct.unpack_from("!2f", fields[2], 4))

    assert decoded_vectors == pytest.approx([(0.25, -0.5), (1.0, 0.125)])


def test_pgvector_store_routes_artifact_vectors_to_binary_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import backend.storage.pgvector_store as store_module

    artifact_store = EmbeddingArtifactStore(tmp_path)
    artifact_id = "f" * 64
    artifact_store.put(artifact_id, [[0.1, 0.2], [0.3, 0.4]])
    vectors = artifact_store.vector_sequence(artifact_id, 2, 2)
    documents = [
        Document(page_content="first", metadata={}, id="id-1"),
        Document(page_content="second", metadata={}, id="id-2"),
    ]

    binary_copy = MagicMock()
    monkeypatch.setattr(store_module, "copy_documents", binary_copy)

    copy_connection = MagicMock()
    publish_connection = MagicMock()
    publish_cursor = MagicMock()
    publish_cursor.fetchone.side_effect = [None, ("new-uuid",)]
    publish_connection.cursor.return_value.__enter__.return_value = publish_cursor

    store = PgVectorStore("postgresql://unused")
    cast(Any, store)._create_collection = MagicMock(
        return_value="11111111-1111-1111-1111-111111111111"
    )
    cast(Any, store)._raw_connection = MagicMock(
        side_effect=[copy_connection, publish_connection]
    )
    cast(Any, store).ensure_collection_vector_index = MagicMock()
    cast(Any, store).ensure_optimized_indexes = MagicMock()

    store.put_documents(
        "idx_target",
        documents,
        model_name="custom-2d",
        vectors=vectors,
        metadata={"dimension": 2},
    )

    binary_copy.assert_called_once()
    assert binary_copy.call_args.kwargs["vectors"] is vectors
    copy_connection.commit.assert_called_once()
    publish_connection.commit.assert_called_once()


def test_binary_copy_failure_rolls_back_and_removes_staging_collection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import backend.storage.pgvector_store as store_module

    artifact_store = EmbeddingArtifactStore(tmp_path)
    artifact_id = "1" * 64
    artifact_store.put(artifact_id, [[0.1, 0.2]])
    vectors = artifact_store.vector_sequence(artifact_id, 1, 2)
    monkeypatch.setattr(
        store_module,
        "copy_documents",
        MagicMock(side_effect=RuntimeError("copy failed")),
    )
    copy_connection = MagicMock()
    store = PgVectorStore("postgresql://unused")
    cast(Any, store)._create_collection = MagicMock(
        return_value="11111111-1111-1111-1111-111111111111"
    )
    cast(Any, store)._delete_collection = MagicMock()
    cast(Any, store)._raw_connection = MagicMock(return_value=copy_connection)

    with pytest.raises(PgVectorStoreError, match="배치 적재 실패"):
        store.put_documents(
            "idx_target",
            [Document(page_content="first", metadata={})],
            model_name="custom-2d",
            vectors=vectors,
            metadata={"dimension": 2},
        )

    copy_connection.rollback.assert_called_once()
    cast(Any, store)._delete_collection.assert_called_once()
