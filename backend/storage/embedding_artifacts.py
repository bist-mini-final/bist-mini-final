from __future__ import annotations

import re
import sys
from array import array
from pathlib import Path
from threading import Lock
from typing import Iterable, Iterator, List, Sequence, overload
from uuid import uuid4

from backend.core.settings import EMBEDDING_ARTIFACT_DIR
from modules.common.base_module import ModuleExecutionError

ARTIFACT_ID_PATTERN = re.compile(r"^[a-f0-9]{64}$")


class EmbeddingArtifactVectors(Sequence[List[float]]):
    """Read-only, batch-sliceable view over an on-disk float32 artifact."""

    def __init__(
        self,
        store: EmbeddingArtifactStore,
        artifact_id: str,
        count: int,
        dimension: int,
    ) -> None:
        if not store.is_valid(artifact_id, count, dimension):
            raise ModuleExecutionError(
                "문서 임베딩 아티팩트가 없거나 크기가 DTO와 일치하지 않습니다"
            )
        self._store = store
        self._artifact_id = artifact_id
        self._count = count
        self._dimension = dimension

    def __len__(self) -> int:
        return self._count

    @property
    def dimension(self) -> int:
        """Return the fixed number of float32 values in each vector."""
        return self._dimension

    def iter_raw_batches(self, batch_size: int) -> Iterator[bytes]:
        """Yield contiguous little-endian float32 bytes without Python floats."""
        return self._store.iter_raw_batches(
            self._artifact_id,
            self._count,
            self._dimension,
            batch_size,
        )

    @overload
    def __getitem__(self, index: int) -> List[float]: ...

    @overload
    def __getitem__(self, index: slice) -> List[List[float]]: ...

    def __getitem__(self, index: int | slice) -> List[float] | List[List[float]]:
        if isinstance(index, slice):
            start, stop, step = index.indices(self._count)
            if step != 1:
                return [self[position] for position in range(start, stop, step)]
            return self._store.read_range(
                self._artifact_id,
                start,
                stop,
                self._count,
                self._dimension,
            )
        position = index if index >= 0 else self._count + index
        if position < 0 or position >= self._count:
            raise IndexError(index)
        return self._store.read_range(
            self._artifact_id,
            position,
            position + 1,
            self._count,
            self._dimension,
        )[0]


class EmbeddingArtifactStore:
    """Stores large float vectors outside workflow JSON and passes a stable reference DTO."""

    def __init__(self, directory: Path = EMBEDDING_ARTIFACT_DIR) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def _path(self, artifact_id: str) -> Path:
        if not ARTIFACT_ID_PATTERN.fullmatch(artifact_id):
            raise ModuleExecutionError("유효하지 않은 임베딩 아티팩트 ID입니다")
        return self.directory / f"{artifact_id}.f32"

    def put(self, artifact_id: str, vectors: List[List[float]]) -> None:
        dimension = len(vectors[0]) if vectors else 0
        self.put_streaming(
            artifact_id,
            (vectors,),
            expected_count=len(vectors),
            dimension=dimension,
        )

    def is_valid(self, artifact_id: str, count: int, dimension: int) -> bool:
        """Return whether an artifact exists and exactly matches its DTO shape."""
        path = self._path(artifact_id)
        return (
            count >= 0
            and dimension > 0
            and path.is_file()
            and path.stat().st_size == count * dimension * 4
        )

    def put_streaming(
        self,
        artifact_id: str,
        vector_batches: Iterable[Sequence[Sequence[float]]],
        *,
        expected_count: int,
        dimension: int,
    ) -> None:
        """Atomically persist vectors without materializing the whole workbook in RAM."""
        if expected_count <= 0 or dimension <= 0:
            raise ModuleExecutionError("임베딩 아티팩트의 개수와 차원은 양수여야 합니다")
        path = self._path(artifact_id)
        if self.is_valid(artifact_id, expected_count, dimension):
            return
        temporary_path = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
        written_count = 0
        try:
            with temporary_path.open("wb") as file:
                for batch in vector_batches:
                    for vector in batch:
                        if len(vector) != dimension:
                            raise ModuleExecutionError(
                                "임베딩 벡터 차원이 아티팩트 DTO와 일치하지 않습니다"
                            )
                    written_count += len(batch)
                    values = array(
                        "f",
                        (value for vector in batch for value in vector),
                    )
                    if values.itemsize != 4:
                        raise ModuleExecutionError(
                            "현재 플랫폼의 C float 크기가 float32와 일치하지 않습니다"
                        )
                    # Artifact bytes are explicitly little-endian so cache files
                    # are portable and can be converted to PostgreSQL's network
                    # byte order without materializing Python float objects.
                    if sys.byteorder != "little":
                        values.byteswap()
                    values.tofile(file)
            if written_count != expected_count:
                raise ModuleExecutionError(
                    f"임베딩 개수({written_count})가 예상 개수({expected_count})와 일치하지 않습니다"
                )
            with self._lock:
                if self.is_valid(artifact_id, expected_count, dimension):
                    return
                temporary_path.replace(path)
        finally:
            temporary_path.unlink(missing_ok=True)

    def iter_batches(
        self,
        artifact_id: str,
        count: int,
        dimension: int,
        batch_size: int,
    ) -> Iterator[List[List[float]]]:
        """Read a validated artifact in bounded vector batches."""
        if not self.is_valid(artifact_id, count, dimension):
            raise ModuleExecutionError(
                "문서 임베딩 아티팩트가 없거나 크기가 DTO와 일치하지 않습니다"
            )
        path = self._path(artifact_id)
        effective_batch_size = max(1, batch_size)
        with path.open("rb") as file:
            for start in range(0, count, effective_batch_size):
                current_count = min(effective_batch_size, count - start)
                values = array("f")
                try:
                    values.fromfile(file, current_count * dimension)
                except EOFError as error:
                    raise ModuleExecutionError(
                        "문서 임베딩 아티팩트가 예상보다 짧습니다"
                    ) from error
                if sys.byteorder != "little":
                    values.byteswap()
                yield [
                    list(values[index * dimension : (index + 1) * dimension])
                    for index in range(current_count)
                ]

    def read_range(
        self,
        artifact_id: str,
        start: int,
        stop: int,
        count: int,
        dimension: int,
    ) -> List[List[float]]:
        """Read one contiguous vector range with a single bounded file operation."""
        if not self.is_valid(artifact_id, count, dimension):
            raise ModuleExecutionError(
                "문서 임베딩 아티팩트가 없거나 크기가 DTO와 일치하지 않습니다"
            )
        if start < 0 or stop < start or stop > count:
            raise ModuleExecutionError("임베딩 아티팩트 읽기 범위가 올바르지 않습니다")
        current_count = stop - start
        values = array("f")
        try:
            with self._path(artifact_id).open("rb") as file:
                file.seek(start * dimension * 4)
                values.fromfile(file, current_count * dimension)
        except EOFError as error:
            raise ModuleExecutionError(
                "문서 임베딩 아티팩트가 예상보다 짧습니다"
            ) from error
        if sys.byteorder != "little":
            values.byteswap()
        return [
            list(values[index * dimension : (index + 1) * dimension])
            for index in range(current_count)
        ]

    def vector_sequence(
        self,
        artifact_id: str,
        count: int,
        dimension: int,
    ) -> EmbeddingArtifactVectors:
        """Expose a validated artifact as a lazy sequence for batched DB writers."""
        return EmbeddingArtifactVectors(self, artifact_id, count, dimension)

    def get(
        self,
        artifact_id: str,
        count: int,
        dimension: int,
    ) -> List[List[float]]:
        return [
            vector
            for batch in self.iter_batches(artifact_id, count, dimension, count)
            for vector in batch
        ]

    def iter_raw_batches(
        self,
        artifact_id: str,
        count: int,
        dimension: int,
        batch_size: int,
    ) -> Iterator[bytes]:
        """Stream validated little-endian float32 byte batches from one file handle."""
        if not self.is_valid(artifact_id, count, dimension):
            raise ModuleExecutionError(
                "문서 임베딩 아티팩트가 없거나 크기가 DTO와 일치하지 않습니다"
            )
        effective_batch_size = max(1, batch_size)
        bytes_per_vector = dimension * 4
        with self._path(artifact_id).open("rb") as file:
            for start in range(0, count, effective_batch_size):
                current_count = min(effective_batch_size, count - start)
                expected_bytes = current_count * bytes_per_vector
                raw = file.read(expected_bytes)
                if len(raw) != expected_bytes:
                    raise ModuleExecutionError(
                        "문서 임베딩 아티팩트가 예상보다 짧습니다"
                    )
                yield raw

    def clear(self) -> int:
        removed = 0
        with self._lock:
            for path in self.directory.glob("*.f32"):
                path.unlink()
                removed += 1
        return removed
