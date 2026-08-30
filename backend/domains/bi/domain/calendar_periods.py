from __future__ import annotations

import re
from dataclasses import dataclass
from enum import IntEnum, unique
from typing import Iterable

from .models import BiPeriod, PeriodKind

YEAR_PATTERN = re.compile(r"(?<!\d)(19\d{2}|20\d{2}|21\d{2}|2200)(?!\d)")


@unique
class CalendarQuarter(IntEnum):
    Q1 = 1
    Q2 = 2
    Q3 = 3
    Q4 = 4


@dataclass(frozen=True, slots=True, order=True)
class CalendarPeriod:
    year: int
    quarter: CalendarQuarter | None

    @property
    def axis_label(self) -> str:
        if self.quarter is None:
            return f"{self.year}-FY"
        return f"{self.year}-Q{self.quarter.value}"


@dataclass(frozen=True, slots=True)
class NormalizedFiscalPeriod:
    source: BiPeriod
    calendar_period: CalendarPeriod
    inferred_from_label: bool


def calendar_quarter(month: int) -> CalendarQuarter:
    if not 1 <= month <= 12:
        raise ValueError("month must be between 1 and 12")
    return CalendarQuarter((month - 1) // 3 + 1)


def _label_year(period: BiPeriod) -> int | None:
    match = YEAR_PATTERN.search(f"{period.label} {period.source_label}")
    return int(match.group(1)) if match is not None else None


def normalize_fiscal_period(period: BiPeriod) -> NormalizedFiscalPeriod | None:
    """Normalize an FY period to a global calendar year/quarter axis."""
    if period.kind is not PeriodKind.FY:
        return None
    if period.end_date is not None:
        return NormalizedFiscalPeriod(
            source=period,
            calendar_period=CalendarPeriod(
                year=period.end_date.year,
                quarter=calendar_quarter(period.end_date.month),
            ),
            inferred_from_label=False,
        )
    year = _label_year(period)
    if year is None:
        return None
    return NormalizedFiscalPeriod(
        source=period,
        calendar_period=CalendarPeriod(year=year, quarter=None),
        inferred_from_label=True,
    )


def index_fiscal_periods_by_calendar_year(
    periods: Iterable[BiPeriod],
) -> dict[int, NormalizedFiscalPeriod]:
    """Index FY periods deterministically by calendar year.

    If a malformed source exposes more than one FY in a calendar year, the period
    with the latest known quarter wins. A dated period always wins over a label-only
    period so comparison behavior does not depend on workbook column order.
    """
    indexed: dict[int, NormalizedFiscalPeriod] = {}
    for period in periods:
        normalized = normalize_fiscal_period(period)
        if normalized is None:
            continue
        year = normalized.calendar_period.year
        existing = indexed.get(year)
        normalized_rank = (
            not normalized.inferred_from_label,
            normalized.calendar_period.quarter or 0,
            normalized.source.ordinal,
        )
        existing_rank = (
            not existing.inferred_from_label,
            existing.calendar_period.quarter or 0,
            existing.source.ordinal,
        ) if existing is not None else None
        if existing_rank is None or normalized_rank > existing_rank:
            indexed[year] = normalized
    return indexed


__all__ = [
    "CalendarPeriod",
    "CalendarQuarter",
    "NormalizedFiscalPeriod",
    "calendar_quarter",
    "index_fiscal_periods_by_calendar_year",
    "normalize_fiscal_period",
]

