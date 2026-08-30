"""PostgreSQL adapter for immutable domain snapshots and atomic heads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from psycopg import Error as PsycopgError
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from backend.contracts.snapshots import VersionedSnapshotRecord
from backend.core.settings import PGVECTOR_URL

from .connection_pool import get_pooled_async_connection


@dataclass(frozen=True, slots=True)
class VersionedSnapshotStoreError(RuntimeError):
    operation: str
    reason: str

    def __str__(self) -> str:
        return f"versioned snapshot store {self.operation} failed: {self.reason}"


class PostgresVersionedSnapshotRepository:
    """Persist generic envelopes while domain services validate payloads."""

    def __init__(self, database_url: str = PGVECTOR_URL) -> None:
        self._database_url = database_url

    async def get_current(
        self,
        *,
        domain: str,
        scope_key: str,
    ) -> VersionedSnapshotRecord | None:
        try:
            async with get_pooled_async_connection(self._database_url) as connection:
                async with connection.cursor(row_factory=dict_row) as cursor:
                    await cursor.execute(
                        "SELECT snapshot.snapshot_id, snapshot.domain, snapshot.scope_key, "
                        "snapshot.schema_version, snapshot.source_fingerprint, "
                        "snapshot.snapshot_payload, snapshot.generated_at "
                        "FROM domain_snapshot_heads head "
                        "JOIN domain_snapshots snapshot "
                        "ON snapshot.domain = head.domain "
                        "AND snapshot.scope_key = head.scope_key "
                        "AND snapshot.snapshot_id = head.current_snapshot_id "
                        "WHERE head.domain = %s AND head.scope_key = %s",
                        (domain, scope_key),
                    )
                    row = await cursor.fetchone()
        except PsycopgError as error:
            raise VersionedSnapshotStoreError("get_current", str(error)) from error
        if row is None:
            return None
        return self._record(row)

    async def publish(self, record: VersionedSnapshotRecord) -> None:
        try:
            async with get_pooled_async_connection(self._database_url) as connection:
                async with connection.transaction():
                    async with connection.cursor() as cursor:
                        await cursor.execute(
                            "INSERT INTO domain_snapshots ("
                            "snapshot_id, domain, scope_key, schema_version, "
                            "source_fingerprint, snapshot_payload, generated_at"
                            ") VALUES (%s, %s, %s, %s, %s, %s, %s) "
                            "ON CONFLICT (snapshot_id) DO NOTHING",
                            (
                                record.snapshot_id,
                                record.domain,
                                record.scope_key,
                                record.schema_version,
                                record.source_fingerprint,
                                Jsonb(dict(record.payload)),
                                record.generated_at,
                            ),
                        )
                        await cursor.execute(
                            "INSERT INTO domain_snapshot_heads ("
                            "domain, scope_key, current_snapshot_id, updated_at"
                            ") VALUES (%s, %s, %s, %s) "
                            "ON CONFLICT (domain, scope_key) DO UPDATE SET "
                            "current_snapshot_id = EXCLUDED.current_snapshot_id, "
                            "updated_at = EXCLUDED.updated_at "
                            "WHERE domain_snapshot_heads.updated_at <= EXCLUDED.updated_at",
                            (
                                record.domain,
                                record.scope_key,
                                record.snapshot_id,
                                record.generated_at,
                            ),
                        )
        except PsycopgError as error:
            raise VersionedSnapshotStoreError("publish", str(error)) from error

    @staticmethod
    def _record(row: dict[str, Any]) -> VersionedSnapshotRecord:
        payload = row["snapshot_payload"]
        if not isinstance(payload, dict):
            raise VersionedSnapshotStoreError(
                "decode",
                "snapshot_payload must be a JSON object",
            )
        return VersionedSnapshotRecord(
            snapshot_id=str(row["snapshot_id"]),
            domain=str(row["domain"]),
            scope_key=str(row["scope_key"]),
            schema_version=int(row["schema_version"]),
            source_fingerprint=str(row["source_fingerprint"]),
            payload=payload,
            generated_at=row["generated_at"],
        )


__all__ = [
    "PostgresVersionedSnapshotRepository",
    "VersionedSnapshotStoreError",
]
