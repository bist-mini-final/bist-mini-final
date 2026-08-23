from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Final

import psycopg2
from psycopg2.extras import Json, RealDictCursor
from pydantic import ValidationError

from backend.core.settings import PGVECTOR_URL
from backend.storage.connection_pool import get_pooled_raw_connection

from .materialization_models import BiCompanyIndexEntry
from .models import (
    BiCompany,
    BiDashboardSnapshot,
    BiMaterializationJob,
    BiMaterializationRequest,
    BiMaterializationSource,
    CompanyId,
    IndexId,
    JobId,
    MaterializationStatus,
    SnapshotId,
)

MATERIALIZATION_JOB_COLUMNS: Final = (
    "job_id, company_id, workbook_hash, status, completed_requests, "
    "total_requests, published_snapshot_id, error_code, message, "
    "started_at, updated_at"
)


@dataclass(frozen=True, slots=True)
class BiPostgresStoreError(RuntimeError):
    operation: str
    reason: str

    def __str__(self) -> str:
        return f"BI PostgreSQL store {self.operation} failed: {self.reason}"


@dataclass(frozen=True, slots=True)
class ClaimedBiMaterialization:
    request: BiMaterializationRequest
    job: BiMaterializationJob
    worker_id: str


class PostgresBiStore:
    """Durable BI control-plane store shared by API and Kubernetes workers."""

    def __init__(self, database_url: str = PGVECTOR_URL) -> None:
        self._database_url = database_url

    def enqueue(
        self,
        request: BiMaterializationRequest,
        job: BiMaterializationJob,
    ) -> BiMaterializationJob:
        try:
            with get_pooled_raw_connection(self._database_url) as connection:
                with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        "INSERT INTO bi_companies "
                        "(company_id, display_name, created_at, updated_at) "
                        "VALUES (%s, %s, %s, %s) "
                        "ON CONFLICT (company_id) DO UPDATE SET "
                        "display_name = EXCLUDED.display_name, "
                        "updated_at = EXCLUDED.updated_at",
                        (
                            request.company_id,
                            request.display_name,
                            job.started_at,
                            job.updated_at,
                        ),
                    )
                    cursor.execute(
                        "INSERT INTO bi_materialization_jobs ("
                        "job_id, company_id, workbook_hash, request_payload, status, "
                        "completed_requests, total_requests, published_snapshot_id, "
                        "error_code, message, available_at, started_at, updated_at"
                        ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                        "ON CONFLICT (job_id) DO UPDATE SET "
                        "request_payload = EXCLUDED.request_payload, "
                        "status = EXCLUDED.status, completed_requests = 0, "
                        "total_requests = 0, published_snapshot_id = NULL, "
                        "error_code = NULL, message = NULL, worker_id = NULL, "
                        "available_at = EXCLUDED.available_at, heartbeat_at = NULL, "
                        "started_at = EXCLUDED.started_at, updated_at = EXCLUDED.updated_at "
                        "WHERE bi_materialization_jobs.status = 'failed'",
                        (
                            job.job_id,
                            job.company_id,
                            job.workbook_hash,
                            Json(request.model_dump(mode="json")),
                            job.status.value,
                            job.completed_requests,
                            job.total_requests,
                            job.published_snapshot_id,
                            job.error_code,
                            job.message,
                            job.updated_at,
                            job.started_at,
                            job.updated_at,
                        ),
                    )
                    cursor.execute(
                        f"SELECT {MATERIALIZATION_JOB_COLUMNS} "
                        "FROM bi_materialization_jobs WHERE job_id = %s",
                        (job.job_id,),
                    )
                    row = cursor.fetchone()
                connection.commit()
        except psycopg2.Error as error:
            raise BiPostgresStoreError("enqueue", str(error)) from error
        if row is None:
            raise BiPostgresStoreError("enqueue", "stored job was not found")
        return self._validate_job(row, "enqueue")

    def register_company(self, company: BiCompany) -> None:
        try:
            with get_pooled_raw_connection(self._database_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO bi_companies (company_id, display_name) "
                        "VALUES (%s, %s) ON CONFLICT (company_id) DO UPDATE SET "
                        "display_name = EXCLUDED.display_name, updated_at = NOW()",
                        (company.company_id, company.display_name),
                    )
                connection.commit()
        except psycopg2.Error as error:
            raise BiPostgresStoreError("register_company", str(error)) from error

    def save_job(self, job: BiMaterializationJob) -> None:
        terminal = job.status in (
            MaterializationStatus.READY,
            MaterializationStatus.PARTIAL,
            MaterializationStatus.FAILED,
        )
        try:
            with get_pooled_raw_connection(self._database_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE bi_materialization_jobs SET status = %s, "
                        "completed_requests = %s, total_requests = %s, "
                        "published_snapshot_id = %s, error_code = %s, message = %s, "
                        "worker_id = CASE WHEN %s THEN NULL ELSE worker_id END, "
                        "heartbeat_at = CASE WHEN %s THEN NULL ELSE NOW() END, "
                        "updated_at = %s WHERE job_id = %s",
                        (
                            job.status.value,
                            job.completed_requests,
                            job.total_requests,
                            job.published_snapshot_id,
                            job.error_code,
                            job.message,
                            terminal,
                            terminal,
                            job.updated_at,
                            job.job_id,
                        ),
                    )
                    if cursor.rowcount != 1:
                        raise BiPostgresStoreError(
                            "save_job",
                            f"job was not found: {job.job_id}",
                        )
                connection.commit()
        except psycopg2.Error as error:
            raise BiPostgresStoreError("save_job", str(error)) from error

    def publish(self, snapshot: BiDashboardSnapshot) -> None:
        try:
            with get_pooled_raw_connection(self._database_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO bi_dashboard_snapshots ("
                        "snapshot_id, company_id, workbook_hash, snapshot_payload, generated_at"
                        ") VALUES (%s, %s, %s, %s, %s) "
                        "ON CONFLICT (snapshot_id) DO UPDATE SET "
                        "snapshot_payload = EXCLUDED.snapshot_payload, "
                        "generated_at = EXCLUDED.generated_at",
                        (
                            snapshot.snapshot.snapshot_id,
                            snapshot.company.company_id,
                            snapshot.source.workbook_hash,
                            Json(snapshot.model_dump(mode="json")),
                            snapshot.snapshot.generated_at,
                        ),
                    )
                    cursor.execute(
                        "UPDATE bi_companies SET display_name = %s, "
                        "current_snapshot_id = %s, updated_at = %s "
                        "WHERE company_id = %s "
                        "AND (updated_at IS NULL OR updated_at <= %s)",
                        (
                            snapshot.company.display_name,
                            snapshot.snapshot.snapshot_id,
                            snapshot.snapshot.generated_at,
                            snapshot.company.company_id,
                            snapshot.snapshot.generated_at,
                        ),
                    )
                    if cursor.rowcount != 1:
                        raise BiPostgresStoreError(
                            "publish",
                            f"company was not found: {snapshot.company.company_id}",
                        )
                connection.commit()
        except psycopg2.Error as error:
            raise BiPostgresStoreError("publish", str(error)) from error

    def get_company(self, company_id: CompanyId) -> BiCompany | None:
        row = self._fetchone(
            "SELECT company_id, display_name FROM bi_companies WHERE company_id = %s",
            (company_id,),
            "get_company",
        )
        return BiCompany.model_validate(row) if row is not None else None

    def list_companies(self) -> tuple[BiCompanyIndexEntry, ...]:
        company_rows = self._fetchall(
            "SELECT company_id, display_name, current_snapshot_id "
            "FROM bi_companies ORDER BY display_name, company_id",
            (),
            "list_companies",
        )
        source_rows = self._fetchall(
            "SELECT name AS index_id, cmetadata->>'company_name' AS display_name, "
            "cmetadata->>'file_name' AS file_name, "
            "cmetadata->>'workbook_hash' AS workbook_hash, "
            "cmetadata->>'created_at' AS created_at "
            "FROM langchain_pg_collection "
            "WHERE NULLIF(BTRIM(cmetadata->>'company_name'), '') IS NOT NULL "
            "AND NULLIF(BTRIM(cmetadata->>'file_name'), '') IS NOT NULL "
            "AND (cmetadata->>'workbook_hash') ~ '^[a-f0-9]{64}$'",
            (),
            "list_company_sources",
        )
        persisted = {
            self._company_key(str(row["display_name"])): row
            for row in company_rows
        }
        def _source_priority(row: dict[str, object]) -> tuple[int, str]:
            file_name = str(row.get("file_name") or "").casefold()
            is_preferred_financials = 1 if "v3" in file_name or "ai_dx" in file_name or "golden" in file_name else 0
            created_at = str(row.get("created_at") or "")
            return (is_preferred_financials, created_at)

        latest_sources: dict[str, dict[str, object]] = {}
        for row in source_rows:
            key = self._company_key(str(row["display_name"]))
            current = latest_sources.get(key)
            if current is None or _source_priority(row) > _source_priority(current):
                latest_sources[key] = row

        entries: list[BiCompanyIndexEntry] = []
        represented: set[str] = set()
        for key, source_row in latest_sources.items():
            company_row = persisted.get(key)
            display_name = str(source_row["display_name"]).strip()
            company_id = (
                CompanyId(str(company_row["company_id"]))
                if company_row is not None
                else self._company_id(display_name)
            )
            entries.append(
                BiCompanyIndexEntry(
                    company=BiCompany(
                        company_id=company_id,
                        display_name=display_name,
                    ),
                    source=BiMaterializationSource(
                        file_name=str(source_row["file_name"]),
                        workbook_hash=str(source_row["workbook_hash"]),
                        index_id=IndexId(str(source_row["index_id"])),
                    ),
                    current_snapshot_id=(
                        SnapshotId(str(company_row["current_snapshot_id"]))
                        if company_row is not None
                        and company_row["current_snapshot_id"] is not None
                        else None
                    ),
                )
            )
            represented.add(key)

        for key, company_row in persisted.items():
            if key in represented or company_row["current_snapshot_id"] is None:
                continue
            entries.append(
                BiCompanyIndexEntry(
                    company=BiCompany(
                        company_id=CompanyId(str(company_row["company_id"])),
                        display_name=str(company_row["display_name"]),
                    ),
                    current_snapshot_id=SnapshotId(
                        str(company_row["current_snapshot_id"])
                    ),
                )
            )
        return tuple(
            sorted(
                entries,
                key=lambda entry: (
                    entry.company.display_name.casefold(),
                    str(entry.company.company_id),
                ),
            )
        )

    @staticmethod
    def _company_key(display_name: str) -> str:
        return " ".join(display_name.split()).casefold()

    @classmethod
    def _company_id(cls, display_name: str) -> CompanyId:
        digest = sha256(cls._company_key(display_name).encode("utf-8")).hexdigest()
        return CompanyId(f"company-{digest[:24]}")

    def get_current(self, company_id: CompanyId) -> BiDashboardSnapshot | None:
        row = self._fetchone(
            "SELECT snapshot.snapshot_payload FROM bi_companies company "
            "JOIN bi_dashboard_snapshots snapshot "
            "ON snapshot.snapshot_id = company.current_snapshot_id "
            "WHERE company.company_id = %s",
            (company_id,),
            "get_current",
        )
        return self._validate_snapshot(row, "get_current") if row is not None else None

    def get_current_many(
        self,
        company_ids: tuple[CompanyId, ...],
    ) -> dict[CompanyId, BiDashboardSnapshot]:
        if not company_ids:
            return {}
        rows = self._fetchall(
            "SELECT company.company_id, snapshot.snapshot_payload "
            "FROM bi_companies company JOIN bi_dashboard_snapshots snapshot "
            "ON snapshot.snapshot_id = company.current_snapshot_id "
            "WHERE company.company_id = ANY(%s)",
            (list(company_ids),),
            "get_current_many",
        )
        return {
            CompanyId(str(row["company_id"])): self._validate_snapshot(
                row,
                "get_current_many",
            )
            for row in rows
        }

    def get_snapshot(
        self,
        company_id: CompanyId,
        snapshot_id: SnapshotId,
    ) -> BiDashboardSnapshot | None:
        row = self._fetchone(
            "SELECT snapshot_payload FROM bi_dashboard_snapshots "
            "WHERE company_id = %s AND snapshot_id = %s",
            (company_id, snapshot_id),
            "get_snapshot",
        )
        return self._validate_snapshot(row, "get_snapshot") if row is not None else None

    def get_job(self, job_id: JobId) -> BiMaterializationJob | None:
        row = self._fetchone(
            f"SELECT {MATERIALIZATION_JOB_COLUMNS} "
            "FROM bi_materialization_jobs WHERE job_id = %s",
            (job_id,),
            "get_job",
        )
        return self._validate_job(row, "get_job") if row is not None else None

    def get_latest_job(self, company_id: CompanyId) -> BiMaterializationJob | None:
        row = self._fetchone(
            f"SELECT {MATERIALIZATION_JOB_COLUMNS} "
            "FROM bi_materialization_jobs WHERE company_id = %s "
            "ORDER BY updated_at DESC LIMIT 1",
            (company_id,),
            "get_latest_job",
        )
        return self._validate_job(row, "get_latest_job") if row is not None else None

    def get_latest_jobs(
        self,
        company_ids: tuple[CompanyId, ...],
    ) -> dict[CompanyId, BiMaterializationJob]:
        if not company_ids:
            return {}
        rows = self._fetchall(
            f"SELECT DISTINCT ON (company_id) {MATERIALIZATION_JOB_COLUMNS} "
            "FROM bi_materialization_jobs WHERE company_id = ANY(%s) "
            "ORDER BY company_id, updated_at DESC",
            (list(company_ids),),
            "get_latest_jobs",
        )
        return {
            CompanyId(str(row["company_id"])): self._validate_job(
                row,
                "get_latest_jobs",
            )
            for row in rows
        }

    def find_latest_job(
        self,
        company_id: CompanyId,
    ) -> BiMaterializationJob | None:
        """Return the most recent job for the company regardless of workbook hash.

        This allows callers to detect any in-progress or completed job before
        deciding whether to start a new materialisation.
        """
        row = self._fetchone(
            f"SELECT {MATERIALIZATION_JOB_COLUMNS} "
            "FROM bi_materialization_jobs WHERE company_id = %s "
            "ORDER BY updated_at DESC LIMIT 1",
            (company_id,),
            "find_latest_job",
        )
        return (
            self._validate_job(row, "find_latest_job")
            if row is not None
            else None
        )

    def claim_next_materialization(
        self,
        worker_id: str,
        claimed_at: datetime,
        *,
        stale_after_seconds: int = 180,
    ) -> ClaimedBiMaterialization | None:
        try:
            with get_pooled_raw_connection(self._database_url) as connection:
                with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        "WITH candidate AS (SELECT job_id FROM bi_materialization_jobs "
                        "WHERE (status = %s AND available_at <= %s) OR ("
                        "status IN (%s, %s) AND (heartbeat_at IS NULL OR "
                        "heartbeat_at < %s - (%s * INTERVAL '1 second'))) "
                        "ORDER BY available_at, started_at, job_id "
                        "FOR UPDATE SKIP LOCKED LIMIT 1) "
                        "UPDATE bi_materialization_jobs AS job SET status = %s, "
                        "worker_id = %s, attempt_count = attempt_count + 1, "
                        "heartbeat_at = %s, updated_at = %s FROM candidate "
                        "WHERE job.job_id = candidate.job_id "
                        f"RETURNING {', '.join('job.' + item.strip() for item in MATERIALIZATION_JOB_COLUMNS.split(','))}, "
                        "job.request_payload",
                        (
                            MaterializationStatus.QUEUED.value,
                            claimed_at,
                            MaterializationStatus.PROFILING.value,
                            MaterializationStatus.EXTRACTING.value,
                            claimed_at,
                            stale_after_seconds,
                            MaterializationStatus.PROFILING.value,
                            worker_id,
                            claimed_at,
                            claimed_at,
                        ),
                    )
                    row = cursor.fetchone()
                connection.commit()
        except psycopg2.Error as error:
            raise BiPostgresStoreError("claim", str(error)) from error
        if row is None:
            return None
        try:
            request = BiMaterializationRequest.model_validate(row["request_payload"])
            job = self._validate_job(row, "claim_validate")
        except ValidationError as error:
            raise BiPostgresStoreError("claim_validate", str(error)) from error
        return ClaimedBiMaterialization(request=request, job=job, worker_id=worker_id)

    def heartbeat_materialization(self, job_id: JobId, worker_id: str) -> bool:
        try:
            with get_pooled_raw_connection(self._database_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE bi_materialization_jobs SET heartbeat_at = NOW() "
                        "WHERE job_id = %s AND worker_id = %s "
                        "AND status IN (%s, %s)",
                        (
                            job_id,
                            worker_id,
                            MaterializationStatus.PROFILING.value,
                            MaterializationStatus.EXTRACTING.value,
                        ),
                    )
                    updated = cursor.rowcount == 1
                connection.commit()
        except psycopg2.Error as error:
            raise BiPostgresStoreError("heartbeat", str(error)) from error
        return updated

    def fail_claim(
        self,
        job_id: JobId,
        worker_id: str,
        failed_at: datetime,
        message: str,
    ) -> bool:
        try:
            with get_pooled_raw_connection(self._database_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE bi_materialization_jobs SET status = %s, "
                        "error_code = %s, message = %s, worker_id = NULL, "
                        "heartbeat_at = NULL, updated_at = %s "
                        "WHERE job_id = %s AND worker_id = %s",
                        (
                            MaterializationStatus.FAILED.value,
                            "materialization_worker_failed",
                            message[:500],
                            failed_at,
                            job_id,
                            worker_id,
                        ),
                    )
                    updated = cursor.rowcount == 1
                connection.commit()
        except psycopg2.Error as error:
            raise BiPostgresStoreError("fail_claim", str(error)) from error
        return updated

    def _fetchone(
        self,
        query: str,
        parameters: tuple[object, ...],
        operation: str,
    ) -> dict[str, object] | None:
        rows = self._query(query, parameters, operation, fetch_all=False)
        return rows if isinstance(rows, dict) else None

    def _fetchall(
        self,
        query: str,
        parameters: tuple[object, ...],
        operation: str,
    ) -> list[dict[str, object]]:
        rows = self._query(query, parameters, operation, fetch_all=True)
        return list(rows) if isinstance(rows, list) else []

    def _query(
        self,
        query: str,
        parameters: tuple[object, ...],
        operation: str,
        *,
        fetch_all: bool,
    ) -> dict[str, object] | list[dict[str, object]] | None:
        try:
            with get_pooled_raw_connection(self._database_url) as connection:
                with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(query, parameters)
                    return cursor.fetchall() if fetch_all else cursor.fetchone()
        except psycopg2.Error as error:
            raise BiPostgresStoreError(operation, str(error)) from error

    @staticmethod
    def _validate_job(
        row: object,
        operation: str,
    ) -> BiMaterializationJob:
        try:
            if not isinstance(row, dict):
                raise TypeError("job row is not a mapping")
            return BiMaterializationJob.model_validate(
                {
                    field_name: row[field_name]
                    for field_name in BiMaterializationJob.model_fields
                }
            )
        except (KeyError, TypeError, ValidationError) as error:
            raise BiPostgresStoreError(operation, str(error)) from error

    @staticmethod
    def _validate_snapshot(
        row: dict[str, object],
        operation: str,
    ) -> BiDashboardSnapshot:
        try:
            return BiDashboardSnapshot.model_validate(row["snapshot_payload"])
        except (KeyError, ValidationError) as error:
            raise BiPostgresStoreError(operation, str(error)) from error


__all__ = [
    "BiPostgresStoreError",
    "ClaimedBiMaterialization",
    "PostgresBiStore",
]
