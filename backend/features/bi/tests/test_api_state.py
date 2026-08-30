from datetime import UTC, datetime

import pytest

from backend.features.bi.api_models import (
    BiCompanyListResponse,
    BiCompanySummary,
    BiMaterializationCandidateReason,
)
from backend.features.bi.api_state import build_materialization_candidate
from backend.features.bi.materialization_models import BiCompanyIndexEntry
from backend.features.bi.models import (
    BiCompany,
    BiDashboardSnapshot,
    BiMaterializationJob,
    BiMaterializationSource,
    CompanyId,
    IndexId,
    JobId,
    MaterializationStatus,
    RefreshStatus,
    SnapshotStatus,
)


def company_summary(
    snapshot_status: SnapshotStatus | None,
    refresh_status: RefreshStatus,
) -> BiCompanySummary:
    """
    Create a test company summary with the specified snapshot and refresh statuses.
    
    Parameters:
    	snapshot_status (SnapshotStatus | None): The company's snapshot status.
    	refresh_status (RefreshStatus): The company's refresh status.
    
    Returns:
    	BiCompanySummary: A company summary populated with fixed test metadata and the specified statuses.
    """
    return BiCompanySummary(
        company_id=CompanyId("company-test"),
        display_name="Test Company",
        source=None,
        current_snapshot_id=None,
        snapshot_status=snapshot_status,
        refresh_status=refresh_status,
        updated_at=None,
    )


def test_lists_company_when_ready_snapshot_exists() -> None:
    summary = company_summary(SnapshotStatus.READY, RefreshStatus.IDLE)

    response = BiCompanyListResponse(companies=(summary,))

    assert response.companies == (summary,)


@pytest.mark.parametrize(
    "refresh_status",
    (RefreshStatus.IDLE, RefreshStatus.FAILED),
)
def test_lists_company_when_partial_snapshot_exists(
    refresh_status: RefreshStatus,
) -> None:
    summary = company_summary(SnapshotStatus.PARTIAL, refresh_status)

    response = BiCompanyListResponse(companies=(summary,))

    assert response.companies == (summary,)


@pytest.mark.parametrize(
    "refresh_status",
    (
        RefreshStatus.QUEUED,
        RefreshStatus.INDEXING,
        RefreshStatus.PROFILING,
        RefreshStatus.EXTRACTING,
        RefreshStatus.MATERIALIZING,
    ),
)
def test_lists_company_when_snapshot_generation_is_active(
    refresh_status: RefreshStatus,
) -> None:
    summary = company_summary(None, refresh_status)

    response = BiCompanyListResponse(companies=(summary,))

    assert response.companies == (summary,)


@pytest.mark.parametrize(
    ("snapshot_status", "refresh_status"),
    (
        (None, RefreshStatus.IDLE),
        (None, RefreshStatus.FAILED),
    ),
)
def test_hides_company_when_dashboard_is_not_ready_or_generating(
    snapshot_status: SnapshotStatus | None,
    refresh_status: RefreshStatus,
) -> None:
    """
    Verify that a company is excluded when its dashboard snapshot is unavailable and generation is inactive or has failed.
    
    Parameters:
    	snapshot_status (SnapshotStatus | None): The dashboard snapshot status.
    	refresh_status (RefreshStatus): The snapshot refresh status.
    """
    summary = company_summary(snapshot_status, refresh_status)

    response = BiCompanyListResponse(companies=(summary,))

    assert response.companies == ()


def test_lists_snapshotless_index_as_materialization_candidate() -> None:
    source = BiMaterializationSource(
        file_name="acme.xlsx",
        workbook_hash="a" * 64,
        index_id=IndexId("index-acme"),
    )
    entry = BiCompanyIndexEntry(
        company=BiCompany(company_id=CompanyId("acme"), display_name="ACME"),
        source=source,
    )

    candidate = build_materialization_candidate(entry, None, None)

    assert candidate is not None
    assert candidate.reason is BiMaterializationCandidateReason.NOT_CREATED
    assert candidate.source == source


def test_lists_company_as_source_changed_when_snapshot_uses_old_workbook() -> None:
    source = BiMaterializationSource(
        file_name="acme-v2.xlsx",
        workbook_hash="b" * 64,
        index_id=IndexId("index-acme-v2"),
    )
    entry = BiCompanyIndexEntry(
        company=BiCompany(company_id=CompanyId("acme"), display_name="ACME"),
        source=source,
    )
    old_snapshot = BiDashboardSnapshot.model_construct(
        source=BiMaterializationSource(
            file_name="acme-v1.xlsx",
            workbook_hash="a" * 64,
            index_id=IndexId("index-acme-v1"),
        )
    )

    candidate = build_materialization_candidate(entry, old_snapshot, None)

    assert candidate is not None
    assert candidate.reason is BiMaterializationCandidateReason.SOURCE_CHANGED


@pytest.mark.parametrize(
    "status",
    (
        MaterializationStatus.QUEUED,
        MaterializationStatus.INDEXING,
        MaterializationStatus.PROFILING,
        MaterializationStatus.EXTRACTING,
        MaterializationStatus.MATERIALIZING,
    ),
)
def test_hides_candidate_while_current_source_is_materializing(
    status: MaterializationStatus,
) -> None:
    source = BiMaterializationSource(
        file_name="acme.xlsx",
        workbook_hash="a" * 64,
        index_id=IndexId("index-acme"),
    )
    entry = BiCompanyIndexEntry(
        company=BiCompany(company_id=CompanyId("acme"), display_name="ACME"),
        source=source,
    )
    now = datetime(2026, 8, 29, tzinfo=UTC)
    job = BiMaterializationJob(
        job_id=JobId("job-acme"),
        company_id=CompanyId("acme"),
        workbook_hash=source.workbook_hash,
        status=status,
        completed_requests=0,
        total_requests=0,
        started_at=now,
        updated_at=now,
    )

    assert build_materialization_candidate(entry, None, job) is None


def test_lists_failed_current_source_as_retry_candidate() -> None:
    source = BiMaterializationSource(
        file_name="acme.xlsx",
        workbook_hash="a" * 64,
        index_id=IndexId("index-acme"),
    )
    entry = BiCompanyIndexEntry(
        company=BiCompany(company_id=CompanyId("acme"), display_name="ACME"),
        source=source,
    )
    now = datetime(2026, 8, 29, tzinfo=UTC)
    job = BiMaterializationJob(
        job_id=JobId("job-acme"),
        company_id=CompanyId("acme"),
        workbook_hash=source.workbook_hash,
        status=MaterializationStatus.FAILED,
        completed_requests=0,
        total_requests=0,
        started_at=now,
        updated_at=now,
    )

    candidate = build_materialization_candidate(entry, None, job)

    assert candidate is not None
    assert candidate.reason is BiMaterializationCandidateReason.FAILED
