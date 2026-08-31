"""PostgreSQL persistence for shared workbook profiles."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256

import psycopg2
from psycopg2.extras import Json, RealDictCursor
from pydantic import ValidationError

from backend.core.settings import PGVECTOR_URL
from backend.domains.data_sources.domain.workbook_profiles import WorkbookProfile
from backend.platform.postgres.pool import get_pooled_raw_connection


class WorkbookProfileRepositoryError(RuntimeError):
    pass


class PostgresWorkbookProfileRepository:
    def __init__(self, database_url: str = PGVECTOR_URL) -> None:
        self._database_url = database_url

    def get(
        self,
        *,
        workbook_hash: str,
        index_id: str,
        profile_version: str | None = None,
    ) -> WorkbookProfile | None:
        parameters: tuple[str, ...]
        version_clause = ""
        if profile_version is None:
            parameters = (workbook_hash, index_id)
        else:
            version_clause = "AND profile_version = %s "
            parameters = (workbook_hash, index_id, profile_version)
        try:
            with get_pooled_raw_connection(self._database_url) as connection:
                with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        "SELECT profile_payload FROM workbook_profiles "
                        "WHERE workbook_hash = %s AND index_id = %s "
                        + version_clause
                        + "ORDER BY updated_at DESC LIMIT 1",
                        parameters,
                    )
                    row = cursor.fetchone()
        except psycopg2.Error as error:
            raise WorkbookProfileRepositoryError(str(error)) from error
        if row is None:
            return None
        try:
            return WorkbookProfile.model_validate(row["profile_payload"])
        except ValidationError as error:
            raise WorkbookProfileRepositoryError(str(error)) from error

    def save(
        self,
        profile: WorkbookProfile,
        *,
        saved_at: datetime | None = None,
    ) -> WorkbookProfile:
        timestamp = saved_at or datetime.now(timezone.utc)
        profile_id = self.profile_id(profile)
        try:
            with get_pooled_raw_connection(self._database_url) as connection:
                with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        "INSERT INTO workbook_profiles (profile_id, workbook_hash, index_id, "
                        "profile_version, status, profile_payload, created_at, updated_at) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                        "ON CONFLICT (workbook_hash, index_id, profile_version) DO UPDATE SET "
                        "status = EXCLUDED.status, profile_payload = EXCLUDED.profile_payload, "
                        "updated_at = EXCLUDED.updated_at "
                        "RETURNING profile_payload",
                        (
                            profile_id,
                            profile.workbook_hash,
                            profile.index_id,
                            profile.profile_version,
                            profile.status,
                            Json(profile.model_dump(mode="json")),
                            timestamp,
                            timestamp,
                        ),
                    )
                    row = cursor.fetchone()
                connection.commit()
        except psycopg2.Error as error:
            raise WorkbookProfileRepositoryError(str(error)) from error
        if row is None:
            raise WorkbookProfileRepositoryError("stored workbook profile was not returned")
        return WorkbookProfile.model_validate(row["profile_payload"])

    @staticmethod
    def profile_id(profile: WorkbookProfile) -> str:
        identity = f"{profile.workbook_hash}:{profile.index_id}:{profile.profile_version}"
        return "workbook-profile-" + sha256(identity.encode("utf-8")).hexdigest()[:24]


__all__ = ["PostgresWorkbookProfileRepository", "WorkbookProfileRepositoryError"]
