"""Shared-volume artifacts exchanged by ingestion coordinator and shard Jobs."""

from __future__ import annotations

import json
import shutil
import sys
from array import array
from pathlib import Path
from threading import Lock
from typing import Any, Mapping, Sequence
from uuid import uuid4

from backend.storage.embedding_artifacts import EmbeddingArtifactStore
from modules.common.exceptions import ModuleExecutionError


class IngestionShardArtifactStore:
    """Persist deterministic shard inputs and float32 outputs atomically."""

    def __init__(self, embedding_store: EmbeddingArtifactStore) -> None:
        self.embedding_store = embedding_store
        self.directory = embedding_store.directory / "shards"
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    @staticmethod
    def _validate_artifact_id(artifact_id: str) -> None:
        if len(artifact_id) != 64 or any(character not in "0123456789abcdef" for character in artifact_id):
            raise ModuleExecutionError("유효하지 않은 ingestion shard artifact ID입니다")

    def _manifest_path(self, artifact_id: str, shard_index: int) -> Path:
        self._validate_artifact_id(artifact_id)
        if shard_index < 0:
            raise ModuleExecutionError("ingestion shard index는 음수일 수 없습니다")
        return self.directory / f"{artifact_id}.{shard_index:06d}.items.json"

    def _vector_path(self, artifact_id: str, shard_index: int) -> Path:
        self._validate_artifact_id(artifact_id)
        if shard_index < 0:
            raise ModuleExecutionError("ingestion shard index는 음수일 수 없습니다")
        return self.directory / f"{artifact_id}.{shard_index:06d}.f32"

    def put_manifest(
        self,
        artifact_id: str,
        shard_index: int,
        items: Sequence[Mapping[str, Any]],
    ) -> Path:
        """Write one complete module-input shard using atomic replacement."""

        path = self._manifest_path(artifact_id, shard_index)
        payload = json.dumps(
            list(items),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if path.is_file() and path.read_bytes() == payload:
            return path
        temporary = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_bytes(payload)
            with self._lock:
                temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        return path

    def read_manifest(self, artifact_id: str, shard_index: int) -> list[dict[str, Any]]:
        path = self._manifest_path(artifact_id, shard_index)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ModuleExecutionError(
                f"ingestion shard manifest를 읽을 수 없습니다: {path.name}"
            ) from error
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise ModuleExecutionError("ingestion shard manifest 형식이 올바르지 않습니다")
        return payload

    def vector_shard_is_valid(
        self,
        artifact_id: str,
        shard_index: int,
        count: int,
        dimension: int,
    ) -> bool:
        path = self._vector_path(artifact_id, shard_index)
        return (
            count > 0
            and dimension > 0
            and path.is_file()
            and path.stat().st_size == count * dimension * 4
        )

    def put_vector_shard(
        self,
        artifact_id: str,
        shard_index: int,
        vectors: Sequence[Sequence[float]],
        *,
        dimension: int,
    ) -> Path:
        count = len(vectors)
        if count <= 0 or dimension <= 0:
            raise ModuleExecutionError("빈 ingestion vector shard는 저장할 수 없습니다")
        if self.vector_shard_is_valid(artifact_id, shard_index, count, dimension):
            return self._vector_path(artifact_id, shard_index)
        values = array("f")
        for vector in vectors:
            if len(vector) != dimension:
                raise ModuleExecutionError("ingestion vector shard 차원이 일치하지 않습니다")
            values.extend(float(value) for value in vector)
        if values.itemsize != 4:
            raise ModuleExecutionError("현재 플랫폼의 C float 크기가 float32와 다릅니다")
        if sys.byteorder != "little":
            values.byteswap()

        path = self._vector_path(artifact_id, shard_index)
        temporary = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("wb") as file:
                values.tofile(file)
            with self._lock:
                if not self.vector_shard_is_valid(
                    artifact_id,
                    shard_index,
                    count,
                    dimension,
                ):
                    temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        return path

    def assemble_embedding_artifact(
        self,
        artifact_id: str,
        shard_counts: Sequence[int],
        dimension: int,
    ) -> None:
        """Concatenate ordered successful shard files into the canonical artifact."""

        expected_count = sum(shard_counts)
        if self.embedding_store.is_valid(artifact_id, expected_count, dimension):
            return
        target = self.embedding_store._path(artifact_id)
        temporary = target.with_name(f"{target.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("wb") as output:
                for shard_index, count in enumerate(shard_counts):
                    if not self.vector_shard_is_valid(
                        artifact_id,
                        shard_index,
                        count,
                        dimension,
                    ):
                        raise ModuleExecutionError(
                            f"완료된 embedding shard 파일이 없습니다: {shard_index}"
                        )
                    with self._vector_path(artifact_id, shard_index).open("rb") as source:
                        shutil.copyfileobj(source, output, length=1024 * 1024)
            if temporary.stat().st_size != expected_count * dimension * 4:
                raise ModuleExecutionError("조립된 embedding artifact 크기가 올바르지 않습니다")
            with self._lock:
                if not self.embedding_store.is_valid(
                    artifact_id,
                    expected_count,
                    dimension,
                ):
                    temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)

    def clear_operation_shards(self, artifact_id: str) -> int:
        """Remove only part/manifest files for one published content identity."""

        self._validate_artifact_id(artifact_id)
        removed = 0
        for path in self.directory.glob(f"{artifact_id}.*"):
            if path.is_file():
                path.unlink(missing_ok=True)
                removed += 1
        return removed


__all__ = ["IngestionShardArtifactStore"]
