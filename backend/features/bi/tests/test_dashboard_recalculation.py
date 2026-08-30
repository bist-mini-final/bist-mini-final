from datetime import UTC, date, datetime

from backend.domains.bi.domain.materialization_models import (
    BiDocumentProfile,
    BiSnapshotBuildInput,
)
from backend.domains.bi.domain.models import (
    BiDashboardSnapshot,
    BiMaterializationRequest,
    BiMaterializationSource,
    BiPeriod,
    CompanyId,
    IndexId,
    JobId,
    PeriodId,
    PeriodKind,
)
from backend.features.bi.dashboard_recalculation import recalculate_dashboard
from backend.features.bi.queued_materializer import BiQueuedMaterializer
from backend.features.bi.snapshot_builder import BiSnapshotBuilder

AS_OF = datetime(2026, 8, 25, tzinfo=UTC)


class SnapshotStore:
    def __init__(self, current: BiDashboardSnapshot) -> None:
        self.current = current
        self.published: BiDashboardSnapshot | None = None

    def get_current(self, company_id: CompanyId) -> BiDashboardSnapshot | None:
        return self.current

    def publish(self, snapshot: BiDashboardSnapshot) -> None:
        self.published = snapshot


def current_snapshot() -> BiDashboardSnapshot:
    period = BiPeriod(
        period_id=PeriodId("fy-2025"),
        kind=PeriodKind.FY,
        label="FY2025",
        source_label="FY2025",
        end_date=date(2025, 12, 31),
        ordinal=2025,
    )
    profile = BiDocumentProfile(periods=(period,))
    request = BiMaterializationRequest(
        company_id=CompanyId("company-test"),
        display_name="Test Company",
        source=BiMaterializationSource(
            file_name="test.xlsx",
            workbook_hash="a" * 64,
            index_id=IndexId("index-test"),
        ),
    )
    return BiSnapshotBuilder().build(
        BiSnapshotBuildInput(
            request=request,
            job_id=JobId("job-base"),
            profile=profile,
            extracted=BiQueuedMaterializer._pending_results(profile),
            generated_at=AS_OF,
        )
    )


def test_recalculation_publishes_from_snapshot_without_question_repository() -> None:
    base = current_snapshot()
    store = SnapshotStore(base)

    result = recalculate_dashboard(
        store=store,
        company_id=base.company.company_id,
        job_id=JobId("recalculation-test"),
        generated_at=AS_OF.replace(hour=1),
    )

    assert store.published is result
    assert result.source == base.source
    assert result.periods == base.periods
    assert result.refresh.job_id == JobId("recalculation-test")
    assert result.snapshot.snapshot_id != base.snapshot.snapshot_id
