from datetime import datetime
from typing import Final, assert_never

from .models import BiPeriod, PeriodKind

HISTORICAL_FY_LIMIT: Final = 5


def select_current_periods(
    periods: tuple[BiPeriod, ...],
    as_of: datetime,
) -> tuple[BiPeriod, ...]:
    """
    Select historical fiscal-year and last-twelve-month periods as of a given date.
    
    Parameters:
    	periods (tuple[BiPeriod, ...]): Candidate periods to evaluate.
    	as_of (datetime): Date used to determine period eligibility.
    
    Returns:
    	tuple[BiPeriod, ...]: Up to five most recent fiscal-year periods followed by the most recent last-twelve-month period.
    """
    cutoff = as_of.date()
    fiscal_periods: list[BiPeriod] = []
    ltm_periods: list[BiPeriod] = []
    eligible = sorted(
        (period for period in periods if period.end_date is not None and period.end_date <= cutoff),
        key=lambda period: period.ordinal,
    )
    for period in eligible:
        match period.kind:
            case PeriodKind.FY:
                fiscal_periods.append(period)
            case PeriodKind.LTM:
                ltm_periods.append(period)
            case unreachable:
                assert_never(unreachable)
    return (*fiscal_periods[-HISTORICAL_FY_LIMIT:], *ltm_periods[-1:])
