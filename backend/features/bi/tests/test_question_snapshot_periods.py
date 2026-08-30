from datetime import UTC, date, datetime

from backend.domains.bi.domain.materialization_models import (
    BiDocumentProfile,
    BiSnapshotBuildInput,
)
from backend.domains.bi.domain.models import (
    AmountScale,
    BiDashboardSnapshot,
    BiMaterializationJob,
    BiMaterializationRequest,
    BiMaterializationSource,
    BiPeriod,
    CompanyId,
    IndexId,
    JobId,
    MetricId,
    PeriodId,
    PeriodKind,
)
from backend.domains.bi.domain.question_records import (
    BiQuestionJobProgress,
    BiQuestionRecord,
    BiQuestionStatus,
    QuestionId,
    QuestionVersion,
)
from backend.features.bi.question_snapshot import (
    BiQuestionSnapshotMaterializer,
    BiQuestionSnapshotMaterializerServices,
)
from backend.features.bi.queued_materializer import BiQueuedMaterializer
from backend.features.bi.snapshot_builder import BiSnapshotBuilder

AS_OF = datetime(2026, 8, 25, tzinfo=UTC)
REFRESH_JOB_ID = JobId("job-refresh")


def period(period_id: str, year: int, kind: PeriodKind) -> BiPeriod:
    """
    Create a business intelligence period with a year-end date and matching identifier metadata.
    
    Parameters:
        period_id (str): Identifier and label for the period.
        year (int): Year used for the period's end date and ordinal.
        kind (PeriodKind): Period classification.
    
    Returns:
        BiPeriod: The configured business intelligence period.
    """
    return BiPeriod(
        period_id=PeriodId(period_id),
        kind=kind,
        label=period_id,
        source_label=period_id,
        end_date=date(year, 12, 31),
        ordinal=year,
    )


def materialization() -> BiMaterializationRequest:
    """
    Create a test materialization request with fixed company and workbook source metadata.
    
    Returns:
        BiMaterializationRequest: A materialization request for the test company and workbook.
    """
    return BiMaterializationRequest(
        company_id=CompanyId("company-test"),
        display_name="Test Company",
        source=BiMaterializationSource(
            file_name="test.xlsx",
            workbook_hash="a" * 64,
            index_id=IndexId("index-test"),
        ),
    )


class QuestionStore:
    def __init__(self, question: BiQuestionRecord) -> None:
        self._question = question

    def get_job_progress(self, job_id: JobId) -> BiQuestionJobProgress | None:
        """
        Provide the failed progress state for a question job.
        
        Returns:
        	BiQuestionJobProgress: Progress showing one failed question and no queued, running, or completed questions.
        """
        return BiQuestionJobProgress(
            job_id=job_id,
            total_questions=1,
            queued_questions=0,
            running_questions=0,
            completed_questions=0,
            failed_questions=1,
        )

    def list_questions(self, job_id: JobId) -> tuple[BiQuestionRecord, ...]:
        return (self._question,)


class AnswerStore:
    def completed_results(self, job_id: JobId) -> tuple[()]:
        """Return no completed results for the specified job."""
        return ()


class SnapshotStore:
    def __init__(self, current: BiDashboardSnapshot) -> None:
        self._current = current
        self.published: BiDashboardSnapshot | None = None

    def get_current(self, company_id: CompanyId) -> BiDashboardSnapshot | None:
        """Retrieve the current dashboard snapshot for a company.
        
        Returns:
            BiDashboardSnapshot | None: The current snapshot, or `None` if unavailable.
        """
        return self._current

    def publish(self, snapshot: BiDashboardSnapshot) -> None:
        self.published = snapshot

    def get_job(self, job_id: JobId) -> BiMaterializationJob | None:
        return None

    def save_job(self, job: BiMaterializationJob) -> None:
        raise AssertionError("job is unavailable in this fixture")


class FixedClock:
    def now(self) -> datetime:
        return AS_OF


class ProfileStore:
    def __init__(self, profile: BiDocumentProfile) -> None:
        self._profile = profile

    def get(self, request: BiMaterializationRequest) -> BiDocumentProfile | None:
        return self._profile


def test_refresh_snapshot_keeps_only_current_dashboard_periods() -> None:
    fiscal_periods = tuple(period(f"fy-{year}", year, PeriodKind.FY) for year in range(2018, 2026))
    latest_ltm = period("ltm-2025", 2025, PeriodKind.LTM)
    all_periods = (*fiscal_periods, latest_ltm)
    request = materialization()
    profile = BiDocumentProfile(periods=fiscal_periods[-5:])
    base = (
        BiSnapshotBuilder()
        .build(
            BiSnapshotBuildInput(
                request=request,
                job_id=JobId("job-base"),
                profile=profile,
                extracted=BiQueuedMaterializer._pending_results(profile),
                generated_at=AS_OF,
            )
        )
        .model_copy(update={"periods": all_periods})
    )
    question = BiQuestionRecord(
        question_id=QuestionId("question-test"),
        materialization_job_id=REFRESH_JOB_ID,
        company_id=request.company_id,
        workbook_hash=request.source.workbook_hash,
        index_id=request.source.index_id,
        metric_id=MetricId.REVENUE,
        period_id=latest_ltm.period_id,
        question_version=QuestionVersion("2"),
        question_text="test question",
        status=BiQuestionStatus.FAILED,
        attempt_count=1,
        created_at=AS_OF,
        updated_at=AS_OF,
        started_at=AS_OF,
        completed_at=AS_OF,
    )
    snapshot_store = SnapshotStore(base)
    materializer = BiQuestionSnapshotMaterializer(
        BiQuestionSnapshotMaterializerServices(
            questions=QuestionStore(question),
            answers=AnswerStore(),
            store=snapshot_store,
            clock=FixedClock(),
        )
    )

    result = materializer.materialize_if_terminal(REFRESH_JOB_ID)

    assert result is not None
    assert result.periods == (*fiscal_periods[-5:], latest_ltm)
    assert snapshot_store.published is result


def test_refresh_snapshot_applies_persisted_document_units() -> None:
    fiscal_period = period("fy-2025", 2025, PeriodKind.FY)
    request = materialization()
    initial_profile = BiDocumentProfile(periods=(fiscal_period,))
    unit_profile = BiDocumentProfile(
        periods=(fiscal_period,),
        currency="USD",
        scale=AmountScale.MILLIONS,
    )
    base = BiSnapshotBuilder().build(
        BiSnapshotBuildInput(
            request=request,
            job_id=JobId("job-base"),
            profile=initial_profile,
            extracted=BiQueuedMaterializer._pending_results(initial_profile),
            generated_at=AS_OF,
        )
    )
    question = BiQuestionRecord(
        question_id=QuestionId("question-test"),
        materialization_job_id=REFRESH_JOB_ID,
        company_id=request.company_id,
        workbook_hash=request.source.workbook_hash,
        index_id=request.source.index_id,
        metric_id=MetricId.REVENUE,
        period_id=fiscal_period.period_id,
        question_version=QuestionVersion("2"),
        question_text="test question",
        status=BiQuestionStatus.FAILED,
        attempt_count=1,
        created_at=AS_OF,
        updated_at=AS_OF,
        started_at=AS_OF,
        completed_at=AS_OF,
    )
    snapshot_store = SnapshotStore(base)
    materializer = BiQuestionSnapshotMaterializer(
        BiQuestionSnapshotMaterializerServices(
            questions=QuestionStore(question),
            answers=AnswerStore(),
            store=snapshot_store,
            clock=FixedClock(),
            profiles=ProfileStore(unit_profile),
        )
    )

    result = materializer.materialize_if_terminal(REFRESH_JOB_ID)

    assert result is not None
    assert result.metrics[MetricId.REVENUE].currency == "USD"
    assert result.metrics[MetricId.REVENUE].scale is AmountScale.MILLIONS
