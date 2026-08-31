"""Local filesystem adapter for uploaded source files."""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterable, Collection
from pathlib import Path
from uuid import uuid4

from anyio import open_file, to_thread

from backend.domains.data_sources.application.ports import (
    DeletedSourceFile,
    SourceFileStorageLimitExceeded,
    StoredSourceFile,
)


class LocalSourceFileStorage:
    def __init__(self, directory: Path) -> None:
        self._directory = directory

    @staticmethod
    def _safe_name(file_name: str) -> str:
        return Path(file_name).name

    async def save(
        self,
        file_name: str,
        chunks: AsyncIterable[bytes],
        *,
        max_size_bytes: int,
    ) -> StoredSourceFile:
        safe_name = self._safe_name(file_name)
        destination = self._directory / safe_name
        temporary = self._directory / f".{safe_name}.{uuid4().hex}.uploading"
        self._directory.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size_bytes = 0
        try:
            async with await open_file(temporary, "wb") as buffer:
                async for chunk in chunks:
                    size_bytes += len(chunk)
                    if size_bytes > max_size_bytes:
                        raise SourceFileStorageLimitExceeded(max_size_bytes)
                    digest.update(chunk)
                    await buffer.write(chunk)
            await to_thread.run_sync(temporary.replace, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return StoredSourceFile(
            file_name=safe_name,
            path=destination,
            size_bytes=size_bytes,
            sha256=digest.hexdigest(),
        )

    def delete(
        self,
        file_name: str,
        *,
        hash_suffixes: Collection[str],
    ) -> DeletedSourceFile:
        safe_name = self._safe_name(file_name)
        target = self._directory / safe_name
        if not target.is_file():
            raise FileNotFoundError(target)
        digest: str | None = None
        if target.suffix.casefold() in hash_suffixes:
            hasher = hashlib.sha256()
            with target.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    hasher.update(chunk)
            digest = hasher.hexdigest()
        target.unlink()
        return DeletedSourceFile(file_name=safe_name, sha256=digest)

    def resolve_existing(self, file_name: str) -> Path | None:
        target = self._directory / self._safe_name(file_name)
        return target if target.is_file() else None


__all__ = ["LocalSourceFileStorage"]
