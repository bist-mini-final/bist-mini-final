import pytest

from backend.features.bi.api_models import BiCompanyListResponse, BiCompanySummary
from backend.features.bi.models import (
    CompanyId,
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
