"""Application service for source-file lifecycle and ingestion submission."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from zipfile import BadZipFile, ZipFile

from anyio import to_thread

from backend.shared.domain import (
    ApplicationInternalError,
    ApplicationValidationError,
    PayloadTooLargeError,
    ResourceNotFoundError,
)

from .ports import SourceFileStorageLimitExceeded, SourceFileStoragePort

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


class DataSourceFileTypeUnsupported(ApplicationValidationError):
    code = "DATA_SOURCE_FILE_TYPE_UNSUPPORTED"


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


class DataSourceFileService:
    def __init__(
        self,
        *,
        storage: SourceFileStoragePort,
        metadata: SourceFileMetadataPort,
        vector_indexes: VectorIndexCleanupPort,
        ingestion: IngestionSubmissionPort,
        inspector: SourceFileInspectorPort,
    ) -> None:
        self._storage = storage
        self._metadata = metadata
        self._vector_indexes = vector_indexes
        self._ingestion = ingestion
        self._inspector = inspector

    async def upload(
        self,
        command: UploadSourceFileCommand,
        chunks: AsyncIterable[bytes],
    ) -> dict[str, Any]:
        suffix = Path(command.file_name).suffix.casefold()
        if suffix not in WORKBOOK_SUFFIXES:
            raise DataSourceFileTypeUnsupported(
                "데이터 소스는 .xlsx 또는 .xlsm 파일만 업로드할 수 있습니다."
            )
        try:
            stored = await self._storage.save(
                command.file_name,
                chunks,
                max_size_bytes=MAX_UPLOAD_SIZE_BYTES,
            )
        except SourceFileStorageLimitExceeded as error:
            raise DataSourceFileTooLarge("파일 크기는 500MB를 초과할 수 없습니다.") from error
        except Exception as error:
            raise DataSourceFileWriteError(f"파일 저장 실패: {error}") from error

        safe_filename = stored.file_name
        destination = stored.path
        size_bytes = stored.size_bytes
        file_hash = stored.sha256

        valid_workbook = await to_thread.run_sync(
            self._is_openxml_workbook,
            destination,
        )
        if not valid_workbook:
            try:
                self._storage.delete(safe_filename, hash_suffixes=())
            except Exception:
                logger.exception("유효하지 않은 업로드 파일 정리 실패: %s", safe_filename)
            raise DataSourceFileTypeUnsupported(
                "파일 확장자와 내용이 일치하는 Open XML Excel 파일이 아닙니다."
            )

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
                workbook_hash=(file_hash if suffix in HASHED_FILE_SUFFIXES else None),
            )
        )
        return {
            "status": "success",
            "file": uploaded,
            "ingestion_job": ingestion_job,
            "error": ingestion_error,
        }

    @staticmethod
    def _is_openxml_workbook(path: Path) -> bool:
        try:
            with ZipFile(path) as workbook:
                workbook.getinfo("[Content_Types].xml")
                workbook.getinfo("xl/workbook.xml")
        except (BadZipFile, KeyError, OSError):
            return False
        return True

    def delete(
        self,
        file_name: str,
        *,
        actor_id: str,
        request_id: str | None,
    ) -> dict[str, Any]:
        try:
            deleted = self._storage.delete(
                file_name,
                hash_suffixes=HASHED_FILE_SUFFIXES,
            )
        except FileNotFoundError:
            raise DataSourceFileNotFound("파일을 찾을 수 없습니다.")
        except Exception as error:
            raise DataSourceFileWriteError(f"파일 삭제 실패: {error}") from error

        safe_filename = deleted.file_name
        workbook_hash = deleted.sha256

        deleted_indexes = 0
        if workbook_hash and self._vector_indexes.is_connected():
            try:
                deleted_indexes = self._vector_indexes.delete_by_workbook_hash(workbook_hash)
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
    "DataSourceFileTypeUnsupported",
    "DataSourceFileWriteError",
    "UploadSourceFileCommand",
]
