from hashlib import sha256
from typing import assert_never

from .api_models import BiCompanySummary, BiMaterializationAccepted
from .catalog import CATALOG_VERSION, FORMULA_VERSION
from .materialization_models import BiCompanyIndexEntry
from .models import (
    BiDashboardSnapshot,
    BiMaterializationJob,
    BiMaterializationRequest,
    BiRefreshState,
    JobId,
    MaterializationStatus,
    RefreshStatus,
)


def accepted(job: BiMaterializationJob) -> BiMaterializationAccepted:
    return BiMaterializationAccepted(
        job_id=job.job_id,
        status=job.status,
        published_snapshot_id=job.published_snapshot_id,
    )


def build_company_summary(
    entry: BiCompanyIndexEntry,
    snapshot: BiDashboardSnapshot | None,
    latest_job: BiMaterializationJob | None,
) -> BiCompanySummary:
    source = entry.source
    if source is not None:
        if (
            snapshot is not None
            and snapshot.source.workbook_hash != source.workbook_hash
        ):
            snapshot = None
            entry = entry.model_copy(update={"current_snapshot_id": None})
        if (
            latest_job is not None
            and latest_job.workbook_hash != source.workbook_hash
        ):
            latest_job = None
    latest_job = _refresh_job(snapshot, latest_job)
    updated_at = snapshot.snapshot.generated_at if snapshot is not None else None
    if latest_job is not None and (
        updated_at is None or latest_job.updated_at > updated_at
    ):
        updated_at = latest_job.updated_at
    return BiCompanySummary(
        company_id=entry.company.company_id,
        display_name=entry.company.display_name,
        source=entry.source,
        current_snapshot_id=entry.current_snapshot_id,
        snapshot_status=(snapshot.snapshot.status if snapshot is not None else None),
        refresh_status=refresh_status(latest_job),
        updated_at=updated_at,
    )


def job_id_for(request: BiMaterializationRequest) -> JobId:
    identity = ":".join(
        (
            str(request.company_id),
            request.source.workbook_hash,
            CATALOG_VERSION,
            FORMULA_VERSION,
        )
    )
    return JobId("job-" + sha256(identity.encode("utf-8")).hexdigest()[:24])


def is_active(materialization_status: MaterializationStatus) -> bool:
    match materialization_status:
        case (
            MaterializationStatus.QUEUED
            | MaterializationStatus.INDEXING
            | MaterializationStatus.PROFILING
            | MaterializationStatus.EXTRACTING
            | MaterializationStatus.MATERIALIZING
        ):
            return True
        case (
            MaterializationStatus.READY
            | MaterializationStatus.PARTIAL
            | MaterializationStatus.FAILED
        ):
            return False
        case unreachable:
            assert_never(unreachable)


def refresh_status(job: BiMaterializationJob | None) -> RefreshStatus:
    if job is None:
        return RefreshStatus.IDLE
    match job.status:
        case MaterializationStatus.QUEUED:
            return RefreshStatus.QUEUED
        case MaterializationStatus.INDEXING:
            return RefreshStatus.INDEXING
        case MaterializationStatus.PROFILING:
            return RefreshStatus.PROFILING
        case MaterializationStatus.EXTRACTING:
            return RefreshStatus.EXTRACTING
        case MaterializationStatus.MATERIALIZING:
            return RefreshStatus.MATERIALIZING
        case MaterializationStatus.FAILED:
            return RefreshStatus.FAILED
        case MaterializationStatus.READY | MaterializationStatus.PARTIAL:
            return RefreshStatus.IDLE
        case unreachable:
            assert_never(unreachable)


def with_refresh_state(
    snapshot: BiDashboardSnapshot,
    latest_job: BiMaterializationJob | None,
) -> BiDashboardSnapshot:
    latest_job = _refresh_job(snapshot, latest_job)
    if latest_job is None:
        return snapshot
    return snapshot.model_copy(
        update={
            "refresh": BiRefreshState(
                status=refresh_status(latest_job),
                job_id=latest_job.job_id,
                started_at=latest_job.started_at,
                message=latest_job.message,
            )
        }
    )


def _refresh_job(
    snapshot: BiDashboardSnapshot | None,
    latest_job: BiMaterializationJob | None,
) -> BiMaterializationJob | None:
    if snapshot is None or latest_job is None:
        return latest_job
    if latest_job.updated_at > snapshot.snapshot.generated_at:
        return latest_job
    return None
