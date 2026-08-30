from datetime import UTC, date, datetime

from backend.domains.bi.domain.current_periods import select_current_periods
from backend.domains.bi.domain.materialization_models import (
    BiDocumentProfile,
    BiSnapshotBuildInput,
)
from backend.domains.bi.domain.models import (
    BiMaterializationRequest,
    BiMaterializationSource,
    BiPeriod,
    CompanyId,
    IndexId,
    JobId,
    PeriodId,
    PeriodKind,
)
from backend.domains.bi.domain.question_batch import BiQuestionBatchPlan
from backend.features.bi.question_service import build_current_question_batch
from backend.features.bi.snapshot_projection import project_build_input

AS_OF = datetime(2026, 8, 24, tzinfo=UTC)


def period(period_id: str, end_date: date | None, ordinal: int) -> BiPeriod:
    """
    Create a business-intelligence period from its identifier and metadata.
    
    Parameters:
        period_id (str): Period identifier; identifiers beginning with ``ltm-`` are classified as LTM periods.
        end_date (date | None): Period end date, if available.
        ordinal (int): Ordering value for the period.
    
    Returns:
        BiPeriod: The constructed period.
    """
    return BiPeriod(
        period_id=PeriodId(period_id),
        kind=PeriodKind.LTM if period_id.startswith("ltm-") else PeriodKind.FY,
        label=period_id,
        source_label=period_id,
        end_date=end_date,
        ordinal=ordinal,
    )


def materialization() -> BiMaterializationRequest:
    """
    Create a test materialization request with fixed company, workbook, and index metadata.
    
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


def test_selects_dated_periods_ending_on_or_before_as_of() -> None:
    past = period("fy-2025", date(2025, 12, 31), 1)
    current = period("ltm-2026-08-24", date(2026, 8, 24), 2)
    future = period("fy-2026", date(2026, 12, 31), 3)
    undated = period("ltm-undated", None, 4)

    selected = select_current_periods((past, current, future, undated), AS_OF)

    assert selected == (past, current)


def test_selects_latest_five_fiscal_periods_and_latest_ltm() -> None:
    fiscal_periods = tuple(
        period(f"fy-{year}", date(year, 12, 31), year) for year in range(2018, 2026)
    )
    older_ltm = period("ltm-2024", date(2024, 12, 31), 2024)
    latest_ltm = period("ltm-2025", date(2025, 12, 31), 2025)

    selected = select_current_periods(
        (*fiscal_periods, older_ltm, latest_ltm),
        AS_OF,
    )

    assert selected == (*fiscal_periods[-5:], latest_ltm)


def test_question_batch_excludes_future_and_undated_periods() -> None:
    plan = BiQuestionBatchPlan(
        materialization=materialization(),
        periods=(
            period("fy-2025", date(2025, 12, 31), 1),
            period("fy-2026", date(2026, 12, 31), 2),
            period("ltm-undated", None, 3),
        ),
        job_id=JobId("job-test"),
        created_at=AS_OF,
    )

    batch = build_current_question_batch(plan)

    assert {question.period_id for question in batch.questions} == {PeriodId("fy-2025")}
    assert {str(question.question_version) for question in batch.questions} == {"2"}


def test_snapshot_projection_excludes_future_and_undated_periods() -> None:
    past = period("fy-2025", date(2025, 12, 31), 1)
    future = period("fy-2026", date(2026, 12, 31), 2)
    undated = period("ltm-undated", None, 3)
    build_input = BiSnapshotBuildInput(
        request=materialization(),
        job_id=JobId("job-test"),
        profile=BiDocumentProfile(periods=(past, future, undated)),
        extracted=(),
        generated_at=AS_OF,
    )

    projection = project_build_input(build_input)

    assert projection.periods == (past,)
