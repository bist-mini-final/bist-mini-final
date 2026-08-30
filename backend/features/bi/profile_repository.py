from dataclasses import dataclass
from datetime import datetime
from typing import Final, Protocol

import psycopg2
from psycopg2.extras import Json, RealDictCursor
from pydantic import ValidationError

from backend.core.settings import PGVECTOR_URL
from backend.domains.bi.domain.materialization_models import (
    BiDocumentProfile,
    BiProfilingResult,
)
from backend.domains.bi.domain.models import BiMaterializationRequest, BiMaterializationSource
from backend.storage.connection_pool import get_pooled_raw_connection

PROFILE_VERSION: Final = "7"


class BiProfileClockPort(Protocol):
    def now(self) -> datetime: ...


class BiDocumentProfilerPort(Protocol):
    def profile(self, request: BiMaterializationRequest) -> BiProfilingResult: ...


class BiDocumentProfileRepositoryPort(Protocol):
    def get(
        self,
        request: BiMaterializationRequest,
    ) -> BiDocumentProfile | None: ...

    def save(
        self,
        request: BiMaterializationRequest,
        profile: BiDocumentProfile,
        saved_at: datetime,
    ) -> BiDocumentProfile: ...


@dataclass(frozen=True, slots=True)
class BiDocumentProfileRepositoryError(RuntimeError):
    operation: str
    reason: str

    def __str__(self) -> str:
        return f"BI document profile {self.operation} failed: {self.reason}"


class PostgresBiDocumentProfileRepository:
    def __init__(
        self,
        database_url: str = PGVECTOR_URL,
        profile_version: str = PROFILE_VERSION,
    ) -> None:
        self._database_url = database_url
        self._profile_version = profile_version

    def get(
        self,
        request: BiMaterializationRequest,
    ) -> BiDocumentProfile | None:
        try:
            with get_pooled_raw_connection(self._database_url) as connection:
                with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        "SELECT profile_payload FROM bi_document_profiles "
                        "WHERE company_id = %s AND workbook_hash = %s "
                        "AND index_id = %s AND profile_version = %s",
                        self._identity(request),
                    )
                    row = cursor.fetchone()
        except psycopg2.Error as error:
            raise BiDocumentProfileRepositoryError("read", str(error)) from error
        if row is None:
            return None
        try:
            return BiDocumentProfile.model_validate(row["profile_payload"])
        except ValidationError as error:
            raise BiDocumentProfileRepositoryError("validate", str(error)) from error

    def get_for_source(
        self,
        source: BiMaterializationSource,
    ) -> BiDocumentProfile | None:
        try:
            with get_pooled_raw_connection(self._database_url) as connection:
                with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        "SELECT profile_payload FROM bi_document_profiles "
                        "WHERE workbook_hash = %s AND index_id = %s "
                        "AND profile_version = %s "
                        "ORDER BY updated_at DESC LIMIT 1",
                        (
                            source.workbook_hash,
                            source.index_id,
                            self._profile_version,
                        ),
                    )
                    row = cursor.fetchone()
        except psycopg2.Error as error:
            raise BiDocumentProfileRepositoryError("read", str(error)) from error
        if row is None:
            return None
        try:
            return BiDocumentProfile.model_validate(row["profile_payload"])
        except ValidationError as error:
            raise BiDocumentProfileRepositoryError("validate", str(error)) from error

    def save(
        self,
        request: BiMaterializationRequest,
        profile: BiDocumentProfile,
        saved_at: datetime,
    ) -> BiDocumentProfile:
        try:
            with get_pooled_raw_connection(self._database_url) as connection:
                with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        "INSERT INTO bi_document_profiles (company_id, workbook_hash, "
                        "index_id, profile_version, profile_payload, created_at, updated_at) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                        "ON CONFLICT (company_id, workbook_hash, index_id, profile_version) "
                        "DO NOTHING",
                        (
                            *self._identity(request),
                            Json(profile.model_dump(mode="json")),
                            saved_at,
                            saved_at,
                        ),
                    )
                    cursor.execute(
                        "SELECT profile_payload FROM bi_document_profiles "
                        "WHERE company_id = %s AND workbook_hash = %s "
                        "AND index_id = %s AND profile_version = %s",
                        self._identity(request),
                    )
                    row = cursor.fetchone()
                connection.commit()
        except psycopg2.Error as error:
            raise BiDocumentProfileRepositoryError("save", str(error)) from error
        if row is None:
            raise BiDocumentProfileRepositoryError("save", "stored row was not found")
        try:
            return BiDocumentProfile.model_validate(row["profile_payload"])
        except ValidationError as error:
            raise BiDocumentProfileRepositoryError("validate", str(error)) from error

    def _identity(self, request: BiMaterializationRequest) -> tuple[str, ...]:
        return (
            str(request.company_id),
            request.source.workbook_hash,
            str(request.source.index_id),
            self._profile_version,
        )


class PersistedBiDocumentProfiler:
    def __init__(
        self,
        delegate: BiDocumentProfilerPort,
        repository: BiDocumentProfileRepositoryPort,
        clock: BiProfileClockPort,
    ) -> None:
        self._delegate = delegate
        self._repository = repository
        self._clock = clock

    def profile(self, request: BiMaterializationRequest) -> BiProfilingResult:
        stored = self._repository.get(request)
        if stored is not None:
            return stored
        profiled = self._delegate.profile(request)
        if not isinstance(profiled, BiDocumentProfile):
            return profiled
        return self._repository.save(request, profiled, self._clock.now())
