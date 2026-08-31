from datetime import date

from backend.domains.bi.domain.calendar_periods import (
    CalendarPeriod,
    CalendarQuarter,
    index_fiscal_periods_by_calendar_year,
    normalize_fiscal_period,
)
from backend.domains.bi.domain.models import BiPeriod, PeriodId, PeriodKind


def period(
    period_id: str,
    *,
    label: str,
    end_date: date | None,
    ordinal: int = 1,
) -> BiPeriod:
    return BiPeriod(
        period_id=PeriodId(period_id),
        kind=PeriodKind.FY,
        label=label,
        source_label=label,
        end_date=end_date,
        ordinal=ordinal,
    )


def test_fiscal_year_end_is_normalized_to_global_calendar_quarter() -> None:
    march = normalize_fiscal_period(
        period("fy-2025-march", label="FY 2025", end_date=date(2025, 3, 31))
    )
    december = normalize_fiscal_period(
        period("fy-2025-dec", label="FY 2025", end_date=date(2025, 12, 31))
    )

    assert march is not None
    assert march.calendar_period == CalendarPeriod(2025, CalendarQuarter.Q1)
    assert march.calendar_period.axis_label == "2025-Q1"
    assert december is not None
    assert december.calendar_period == CalendarPeriod(2025, CalendarQuarter.Q4)


def test_undated_period_uses_explicit_fallback_axis() -> None:
    normalized = normalize_fiscal_period(
        period("fy-2024", label="Fiscal year 2024", end_date=None)
    )

    assert normalized is not None
    assert normalized.calendar_period == CalendarPeriod(2024, None)
    assert normalized.calendar_period.axis_label == "2024-FY"
    assert normalized.inferred_from_label is True


def test_calendar_year_index_is_deterministic_for_duplicate_source_periods() -> None:
    indexed = index_fiscal_periods_by_calendar_year(
        (
            period("fy-2025-label", label="2025", end_date=None, ordinal=3),
            period(
                "fy-2025-march", label="2025", end_date=date(2025, 3, 31), ordinal=1
            ),
            period(
                "fy-2025-dec", label="2025", end_date=date(2025, 12, 31), ordinal=2
            ),
        )
    )

    assert indexed[2025].source.period_id == "fy-2025-dec"
