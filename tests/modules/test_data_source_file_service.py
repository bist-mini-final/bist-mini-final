from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from backend.domains.data_sources.application import (
    DataSourceFileService,
    DataSourceFileTooLarge,
    DataSourceFileTypeUnsupported,
    UploadSourceFileCommand,
)
from backend.domains.data_sources.infrastructure.filesystem import LocalSourceFileStorage


class FakeMetadata:
    def __init__(self) -> None:
        self.saved: dict[str, Any] | None = None
        self.deleted: str | None = None

    async def is_connected_async(self) -> bool:
        return True

    async def save_source_file_async(self, **values: Any) -> None:
        self.saved = values

    def is_connected(self) -> bool:
        return True

    def delete_source_file(
        self,
        file_id_hash_or_name: str,
        *,
        actor_id: str,
        request_id: str | None,
    ) -> bool:
        del actor_id, request_id
        self.deleted = file_id_hash_or_name
        return True


class FakeVectors:
    def __init__(self) -> None:
        self.deleted_hash: str | None = None

    def is_connected(self) -> bool:
        return True

    def delete_by_workbook_hash(self, workbook_hash: str) -> int:
        self.deleted_hash = workbook_hash
        return 2


class FakeIngestion:
    def submit(
        self,
        *,
        file_name: str,
        model: str,
        batch_size: int,
    ) -> dict[str, Any]:
        return {
            "file_name": file_name,
            "model": model,
            "batch_size": batch_size,
        }


class FakeInspector:
    def file_info(
        self,
        path: Path,
        *,
        workbook_hash: str | None,
    ) -> dict[str, Any]:
        return {
            "file_name": path.name,
            "workbook_hash": workbook_hash,
            "size_bytes": path.stat().st_size,
        }


def _service(tmp_path: Path) -> tuple[DataSourceFileService, FakeMetadata, FakeVectors]:
    metadata = FakeMetadata()
    vectors = FakeVectors()
    return (
        DataSourceFileService(
            storage=LocalSourceFileStorage(tmp_path),
            metadata=metadata,
            vector_indexes=vectors,
            ingestion=FakeIngestion(),
            inspector=FakeInspector(),
        ),
        metadata,
        vectors,
    )


def _workbook_bytes() -> bytes:
    payload = BytesIO()
    with ZipFile(payload, "w", compression=ZIP_DEFLATED) as workbook:
        workbook.writestr("[Content_Types].xml", "<Types />")
        workbook.writestr("xl/workbook.xml", "<workbook />")
    return payload.getvalue()


def test_upload_persists_metadata_and_submits_ingestion(tmp_path: Path) -> None:
    service, metadata, _ = _service(tmp_path)
    workbook_payload = _workbook_bytes()

    async def chunks():
        yield workbook_payload

    result = asyncio.run(
        service.upload(
            UploadSourceFileCommand(
                file_name="sample.xlsx",
                auto_ingest=True,
                model="embedding-model",
                batch_size=32,
            ),
            chunks(),
        )
    )

    assert (tmp_path / "sample.xlsx").read_bytes() == workbook_payload
    assert metadata.saved is not None
    assert result["ingestion_job"]["batch_size"] == 32


def test_upload_rejects_oversized_stream_without_partial_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _, _ = _service(tmp_path)
    monkeypatch.setattr(
        "backend.domains.data_sources.application.files.MAX_UPLOAD_SIZE_BYTES",
        3,
    )

    async def chunks():
        yield b"toolarge"

    with pytest.raises(DataSourceFileTooLarge):
        asyncio.run(
            service.upload(
                UploadSourceFileCommand(
                    file_name="large.xlsx",
                    auto_ingest=False,
                    model="embedding-model",
                    batch_size=32,
                ),
                chunks(),
            )
        )
    assert not list(tmp_path.iterdir())


def test_upload_rejects_unsupported_extension_before_writing(tmp_path: Path) -> None:
    service, _, _ = _service(tmp_path)

    async def chunks():
        yield b"not-a-workbook"

    with pytest.raises(DataSourceFileTypeUnsupported):
        asyncio.run(
            service.upload(
                UploadSourceFileCommand(
                    file_name="payload.exe",
                    auto_ingest=False,
                    model="embedding-model",
                    batch_size=32,
                ),
                chunks(),
            )
        )
    assert not list(tmp_path.iterdir())


def test_upload_rejects_spoofed_excel_extension_and_removes_file(tmp_path: Path) -> None:
    service, metadata, _ = _service(tmp_path)

    async def chunks():
        yield b"not-a-zip-workbook"

    with pytest.raises(DataSourceFileTypeUnsupported):
        asyncio.run(
            service.upload(
                UploadSourceFileCommand(
                    file_name="payload.xlsx",
                    auto_ingest=False,
                    model="embedding-model",
                    batch_size=32,
                ),
                chunks(),
            )
        )
    assert metadata.saved is None
    assert not list(tmp_path.iterdir())


def test_delete_removes_file_vector_scope_and_metadata(tmp_path: Path) -> None:
    service, metadata, vectors = _service(tmp_path)
    (tmp_path / "sample.xlsx").write_bytes(b"workbook")

    result = service.delete(
        "sample.xlsx",
        actor_id="tester",
        request_id="request-1",
    )

    assert result["deleted_indexes"] == 2
    assert vectors.deleted_hash is not None
    assert metadata.deleted == vectors.deleted_hash
    assert not (tmp_path / "sample.xlsx").exists()
