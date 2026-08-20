import hashlib
import json
import re
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Sequence, Tuple
from uuid import uuid4

from ..core.settings import VECTOR_INDEX_DIR
from ..modules.base import ModuleExecutionError


INDEX_ID_PATTERN = re.compile(r"^[a-f0-9]{64}$")
INDEX_FORMAT_VERSION = "numpy-flat-ip-v1"


class VectorIndexStore:
    """Content-addressed exact cosine index with JSON document metadata.

    The index deliberately uses a plain float32 NumPy matrix instead of loading
    FAISS into the API process.  The previous FAISS implementation brought its
    own OpenMP runtime into a process that also loads Torch and scikit-learn;
    on macOS that combination can segfault inside ``faiss::fvec_renorm_L2`` and
    terminate the whole workflow server.  A flat matrix gives the same exact
    inner-product ranking semantics for the current workbook-sized indexes
    without exposing the DAG runner to that native-process failure mode.
    """

    def __init__(self, directory: Path = VECTOR_INDEX_DIR) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    @staticmethod
    def index_id(artifact_id: str) -> str:
        return hashlib.sha256(
            f"{INDEX_FORMAT_VERSION}:{artifact_id}".encode("utf-8")
        ).hexdigest()

    def _paths(self, index_id: str) -> Tuple[Path, Path]:
        if not INDEX_ID_PATTERN.fullmatch(index_id):
            raise ModuleExecutionError("유효하지 않은 벡터 인덱스 ID입니다")
        return (
            self.directory / f"{index_id}.npy",
            self.directory / f"{index_id}.json",
        )

    @staticmethod
    def _dependencies():
        try:
            import numpy
        except ImportError as error:
            raise ModuleExecutionError(
                "벡터 인덱스 실행에 numpy가 필요합니다"
            ) from error
        return numpy

    def put(
        self,
        index_id: str,
        vectors: Sequence[Sequence[float]],
        metadata: Dict[str, Any],
    ) -> None:
        index_path, metadata_path = self._paths(index_id)
        if index_path.is_file() and metadata_path.is_file():
            stored = self._validate_metadata(index_id, metadata_path)
            self._assert_same_index(metadata, stored)
            return
        if len(vectors) == 0:
            raise ModuleExecutionError("벡터 인덱스에 저장할 문서가 없습니다")

        numpy = self._dependencies()
        matrix = numpy.asarray(vectors, dtype="float32")
        if matrix.ndim != 2 or matrix.shape[1] <= 0:
            raise ModuleExecutionError("벡터 인덱스 입력 차원이 올바르지 않습니다")
        if not numpy.isfinite(matrix).all():
            raise ModuleExecutionError("벡터 인덱스 입력에 유한하지 않은 값이 있습니다")
        norms = numpy.linalg.norm(matrix, axis=1, keepdims=True)
        matrix = numpy.divide(
            matrix,
            norms,
            out=numpy.zeros_like(matrix),
            where=norms > 0,
        )

        document = {
            "index_id": index_id,
            "format": INDEX_FORMAT_VERSION,
            **metadata,
        }
        temporary_id = uuid4().hex
        temporary_index = index_path.with_name(
            f"{index_path.name}.{temporary_id}.tmp"
        )
        temporary_metadata = metadata_path.with_name(
            f"{metadata_path.name}.{temporary_id}.tmp"
        )
        try:
            with temporary_index.open("wb") as file:
                numpy.save(file, matrix, allow_pickle=False)
            temporary_metadata.write_text(
                json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2)
                + "\n",
                encoding="utf-8",
            )
            with self._lock:
                if index_path.is_file() and metadata_path.is_file():
                    stored = self._validate_metadata(index_id, metadata_path)
                    self._assert_same_index(metadata, stored)
                    return
                temporary_index.replace(index_path)
                temporary_metadata.replace(metadata_path)
        finally:
            temporary_index.unlink(missing_ok=True)
            temporary_metadata.unlink(missing_ok=True)

    def metadata(self, index_id: str) -> Dict[str, Any]:
        index_path, metadata_path = self._paths(index_id)
        if not index_path.is_file() or not metadata_path.is_file():
            raise ModuleExecutionError(
                "벡터 인덱스가 없습니다. Vector Index Writer를 다시 실행하세요"
            )
        return self._validate_metadata(index_id, metadata_path)

    def search(
        self,
        index_id: str,
        query_vector: Sequence[float],
        limit: int,
    ) -> List[Tuple[float, Dict[str, Any]]]:
        if limit <= 0:
            return []
        index_path, _ = self._paths(index_id)
        metadata = self.metadata(index_id)
        numpy = self._dependencies()
        try:
            matrix = numpy.load(index_path, allow_pickle=False, mmap_mode="r")
        except (OSError, ValueError) as error:
            raise ModuleExecutionError("벡터 인덱스를 읽을 수 없습니다") from error
        dimension = int(metadata.get("dimension", 0))
        documents = metadata.get("items")
        if (
            matrix.ndim != 2
            or matrix.shape[1] != dimension
            or matrix.shape[0] != len(documents)
        ):
            raise ModuleExecutionError("벡터 인덱스와 메타데이터가 일치하지 않습니다")
        if len(query_vector) != dimension:
            raise ModuleExecutionError(
                "질의 임베딩과 벡터 인덱스 차원이 일치하지 않습니다"
            )
        query = numpy.asarray(query_vector, dtype="float32")
        if not numpy.isfinite(query).all():
            raise ModuleExecutionError("질의 임베딩에 유한하지 않은 값이 있습니다")
        norm = float(numpy.linalg.norm(query))
        if norm > 0:
            query = query / norm
        else:
            query = numpy.zeros_like(query)
        scores = numpy.einsum("ij,j->i", matrix, query, optimize=False)
        result_count = min(limit, int(matrix.shape[0]))
        indices = numpy.argsort(-scores, kind="stable")[:result_count]
        return [
            (float(scores[int(document_index)]), documents[int(document_index)])
            for document_index in indices
        ]

    @staticmethod
    def _validate_metadata(index_id: str, path: Path) -> Dict[str, Any]:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ModuleExecutionError("벡터 인덱스 메타데이터를 읽을 수 없습니다") from error
        if not isinstance(document, dict) or document.get("index_id") != index_id:
            raise ModuleExecutionError("벡터 인덱스 메타데이터 ID가 일치하지 않습니다")
        if document.get("format") != INDEX_FORMAT_VERSION:
            raise ModuleExecutionError("지원하지 않는 벡터 인덱스 형식입니다")
        items = document.get("items")
        if not isinstance(items, list):
            raise ModuleExecutionError("벡터 인덱스 문서 메타데이터가 올바르지 않습니다")
        if int(document.get("document_count", -1)) != len(items):
            raise ModuleExecutionError("벡터 인덱스 문서 개수가 일치하지 않습니다")
        return document

    @staticmethod
    def _assert_same_index(
        requested: Dict[str, Any],
        stored: Dict[str, Any],
    ) -> None:
        identity_fields = (
            "artifact_id",
            "workbook_hash",
            "model",
            "dimension",
            "document_count",
        )
        if any(requested.get(key) != stored.get(key) for key in identity_fields):
            raise ModuleExecutionError(
                "같은 index_id에 다른 벡터 인덱스 메타데이터가 저장되어 있습니다"
            )

    def clear(self) -> int:
        index_ids = {
            path.stem
            for path in self.directory.glob("*.faiss")
            if INDEX_ID_PATTERN.fullmatch(path.stem)
        }
        index_ids.update(
            path.stem
            for path in self.directory.glob("*.npy")
            if INDEX_ID_PATTERN.fullmatch(path.stem)
        )
        index_ids.update(
            path.stem
            for path in self.directory.glob("*.json")
            if INDEX_ID_PATTERN.fullmatch(path.stem)
        )
        with self._lock:
            for index_id in index_ids:
                index_path, metadata_path = self._paths(index_id)
                index_path.unlink(missing_ok=True)
                (self.directory / f"{index_id}.faiss").unlink(missing_ok=True)
                metadata_path.unlink(missing_ok=True)
        return len(index_ids)
