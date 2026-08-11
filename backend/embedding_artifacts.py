from array import array
from pathlib import Path
from threading import Lock
from typing import List
import re

from .config import EMBEDDING_ARTIFACT_DIR
from .modules.base import ModuleExecutionError


ARTIFACT_ID_PATTERN = re.compile(r"^[a-f0-9]{64}$")


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
        path = self._path(artifact_id)
        if path.is_file():
            return
        temporary_path = path.with_suffix(".f32.tmp")
        flattened = array("f", (value for vector in vectors for value in vector))
        with self._lock:
            if path.is_file():
                return
            with temporary_path.open("wb") as file:
                flattened.tofile(file)
            temporary_path.replace(path)

    def get(
        self,
        artifact_id: str,
        count: int,
        dimension: int,
    ) -> List[List[float]]:
        path = self._path(artifact_id)
        if not path.is_file():
            raise ModuleExecutionError(
                "문서 임베딩 아티팩트가 없습니다. Cell Text Embedder를 다시 실행하세요"
            )
        values = array("f")
        try:
            with path.open("rb") as file:
                values.fromfile(file, count * dimension)
        except EOFError as error:
            raise ModuleExecutionError(
                "문서 임베딩 아티팩트가 예상보다 짧습니다"
            ) from error
        if len(values) != count * dimension or path.stat().st_size != count * dimension * 4:
            raise ModuleExecutionError("문서 임베딩 아티팩트 크기가 DTO와 일치하지 않습니다")
        return [
            list(values[index * dimension : (index + 1) * dimension])
            for index in range(count)
        ]

    def clear(self) -> int:
        removed = 0
        with self._lock:
            for path in self.directory.glob("*.f32"):
                path.unlink()
                removed += 1
        return removed
