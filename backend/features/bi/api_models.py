from datetime import datetime
from typing import assert_never

from pydantic import field_validator

from .models import (
    BiContractModel,
    BiMaterializationJob,
    BiMaterializationSource,
    CompanyId,
    JobId,
    MaterializationStatus,
    RefreshStatus,
    SnapshotId,
    SnapshotStatus,
)


class BiCompanySummary(BiContractModel):
    company_id: CompanyId
    display_name: str
    source: BiMaterializationSource | None
    current_snapshot_id: SnapshotId | None
    snapshot_status: SnapshotStatus | None
    refresh_status: RefreshStatus
    updated_at: datetime | None


class BiCompanyListResponse(BiContractModel):
    companies: tuple[BiCompanySummary, ...]

    @field_validator("companies")
    @classmethod
    def keep_dashboard_companies(
        cls,
        companies: tuple[BiCompanySummary, ...],
    ) -> tuple[BiCompanySummary, ...]:
        return tuple(company for company in companies if _should_list_company(company))


class BiDashboardPendingResponse(BiContractModel):
    job: BiMaterializationJob


class BiMaterializationAccepted(BiContractModel):
    job_id: JobId
    status: MaterializationStatus
    published_snapshot_id: SnapshotId | None


def _should_list_company(company: BiCompanySummary) -> bool:
    match company.snapshot_status:
        case SnapshotStatus.READY:
            return True
        case SnapshotStatus.PARTIAL | None:
            match company.refresh_status:
                case (
                    RefreshStatus.QUEUED
                    | RefreshStatus.INDEXING
                    | RefreshStatus.PROFILING
                    | RefreshStatus.EXTRACTING
                    | RefreshStatus.MATERIALIZING
                ):
                    return True
                case RefreshStatus.IDLE | RefreshStatus.FAILED:
                    return False
                case unreachable:
                    assert_never(unreachable)
        case unreachable:
            assert_never(unreachable)
