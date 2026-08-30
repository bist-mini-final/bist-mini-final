"""Application service for source-file lifecycle and ingestion submission."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import AsyncIterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from anyio import open_file, to_thread

from backend.shared.domain import (
    ApplicationInternalError,
    PayloadTooLargeError,
    ResourceNotFoundError,
)

MAX_UPLOAD_SIZE_BYTES = 500 * 1024 * 1024
WORKBOOK_SUFFIXES = frozenset({".xlsx", ".xlsm"})
HASHED_FILE_SUFFIXES = frozenset({".xlsx", ".xlsm", ".json"})
logger = logging.getLogger(__name__)


class DataSourceFileTooLarge(PayloadTooLargeError):
    code = "DATA_SOURCE_FILE_TOO_LARGE"


class DataSourceFileNotFound(ResourceNotFoundError):
    code = "DATA_SOURCE_FILE_NOT_FOUND"


class DataSourceFileWriteError(ApplicationInternalError):
    code = "DATA_SOURCE_FILE_WRITE_FAILED"


class SourceFileMetadataPort(Protocol):
    async def is_connected_async(self) -> bool: ...

    async def save_source_file_async(self, **values: Any) -> None: ...

    def is_connected(self) -> bool: ...

    def delete_source_file(
        self,
        file_id_hash_or_name: str,
        *,
        actor_id: str,
        request_id: str | None,
    ) -> bool: ...


class VectorIndexCleanupPort(Protocol):
    def is_connected(self) -> bool: ...

    def delete_by_workbook_hash(self, workbook_hash: str) -> int: ...


class IngestionSubmissionPort(Protocol):
    def submit(
        self,
        *,
        file_name: str,
        model: str,
        batch_size: int,
    ) -> dict[str, Any]: ...


class SourceFileInspectorPort(Protocol):
    def file_info(
        self,
        path: Path,
        *,
        workbook_hash: str | None,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class UploadSourceFileCommand:
    file_name: str
    auto_ingest: bool
    model: str
    batch_size: int


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class DataSourceFileService:
    def __init__(
        self,
        *,
        processed_dir: Path,
        metadata: SourceFileMetadataPort,
        vector_indexes: VectorIndexCleanupPort,
        ingestion: IngestionSubmissionPort,
        inspector: SourceFileInspectorPort,
    ) -> None:
        self._processed_dir = processed_dir
        self._metadata = metadata
        self._vector_indexes = vector_indexes
        self._ingestion = ingestion
        self._inspector = inspector

    async def upload(
        self,
        command: UploadSourceFileCommand,
        chunks: AsyncIterable[bytes],
    ) -> dict[str, Any]:
        safe_filename = Path(command.file_name).name
        destination = self._processed_dir / safe_filename
        temporary = self._processed_dir / (
            f".{safe_filename}.{uuid4().hex}.uploading"
        )
        try:
            self._processed_dir.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            size_bytes = 0
            async with await open_file(temporary, "wb") as buffer:
                async for chunk in chunks:
                    size_bytes += len(chunk)
                    if size_bytes > MAX_UPLOAD_SIZE_BYTES:
                        raise DataSourceFileTooLarge(
                            "파일 크기는 500MB를 초과할 수 없습니다."
                        )
                    digest.update(chunk)
                    await buffer.write(chunk)
            await to_thread.run_sync(temporary.replace, destination)
            file_hash = digest.hexdigest()
        except DataSourceFileTooLarge:
            temporary.unlink(missing_ok=True)
            raise
        except Exception as error:
            temporary.unlink(missing_ok=True)
            raise DataSourceFileWriteError(f"파일 저장 실패: {error}") from error

        if await self._metadata.is_connected_async():
            try:
                await self._metadata.save_source_file_async(
                    file_id=file_hash,
                    file_name=safe_filename,
                    file_hash=file_hash,
                    file_type=destination.suffix.lstrip(".").lower() or "bin",
                    file_size=size_bytes,
                    storage_path=str(destination.resolve()),
                )
            except Exception as error:
                logger.warning("업로드 파일 DB 메타데이터 저장 실패: %s", error)

        suffix = destination.suffix.casefold()
        ingestion_job: dict[str, Any] | None = None
        ingestion_error: str | None = None
        if command.auto_ingest and suffix in WORKBOOK_SUFFIXES:
            try:
                ingestion_job = await to_thread.run_sync(
                    lambda: self._ingestion.submit(
                    file_name=safe_filename,
                    model=command.model,
                    batch_size=command.batch_size,
                    )
                )
            except Exception as error:
                logger.exception("업로드 후 자동 인덱싱 제출 실패: %s", safe_filename)
                ingestion_error = str(error)

        uploaded = await to_thread.run_sync(
            lambda: self._inspector.file_info(
                destination,
                workbook_hash=(
                    file_hash if suffix in HASHED_FILE_SUFFIXES else None
                ),
            )
        )
        return {
            "status": "success",
            "file": uploaded,
            "ingestion_job": ingestion_job,
            "error": ingestion_error,
        }

    def delete(
        self,
        file_name: str,
        *,
        actor_id: str,
        request_id: str | None,
    ) -> dict[str, Any]:
        safe_filename = Path(file_name).name
        target = self._processed_dir / safe_filename
        if not target.is_file():
            raise DataSourceFileNotFound("파일을 찾을 수 없습니다.")

        workbook_hash: str | None = None
        if target.suffix.lower() in HASHED_FILE_SUFFIXES:
            try:
                workbook_hash = _sha256_file(target)
            except Exception as error:
                logger.warning("파일 해시 계산 실패 (인덱스 정리 건너뜀): %s", error)

        try:
            target.unlink()
        except Exception as error:
            raise DataSourceFileWriteError(f"파일 삭제 실패: {error}") from error

        deleted_indexes = 0
        if workbook_hash and self._vector_indexes.is_connected():
            try:
                deleted_indexes = self._vector_indexes.delete_by_workbook_hash(
                    workbook_hash
                )
            except Exception as error:
                logger.warning(
                    "연관 벡터 인덱스 정리 실패 (파일은 삭제됨): %s",
                    error,
                    exc_info=True,
                )

        if self._metadata.is_connected():
            try:
                self._metadata.delete_source_file(
                    workbook_hash or safe_filename,
                    actor_id=actor_id,
                    request_id=request_id,
                )
            except Exception as error:
                logger.warning(
                    "삭제된 파일 DB 메타데이터 soft-delete 실패: %s",
                    error,
                    exc_info=True,
                )

        return {
            "status": "success",
            "message": f"{safe_filename} 파일이 삭제되었습니다.",
            "deleted_indexes": deleted_indexes,
        }


__all__ = [
    "DataSourceFileNotFound",
    "DataSourceFileService",
    "DataSourceFileTooLarge",
    "DataSourceFileWriteError",
    "UploadSourceFileCommand",
]
