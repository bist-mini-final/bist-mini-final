from datetime import datetime

from .models import (
    BiContractModel,
    BiMaterializationJob,
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
    current_snapshot_id: SnapshotId | None
    snapshot_status: SnapshotStatus | None
    refresh_status: RefreshStatus
    updated_at: datetime | None


class BiCompanyListResponse(BiContractModel):
    companies: tuple[BiCompanySummary, ...]


class BiDashboardPendingResponse(BiContractModel):
    job: BiMaterializationJob


class BiMaterializationAccepted(BiContractModel):
    job_id: JobId
    status: MaterializationStatus
    published_snapshot_id: SnapshotId | None
