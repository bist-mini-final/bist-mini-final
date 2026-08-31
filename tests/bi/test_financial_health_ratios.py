from decimal import Decimal

from backend.domains.bi.domain.calculator import (
    calculate_debt_ratio,
    calculate_free_cash_flow_margin,
    calculate_net_debt_ratio,
)
from backend.domains.bi.domain.models import (
    AvailableObservation,
    MetricStatus,
    PeriodId,
    UnavailableObservation,
)

PERIOD_ID = PeriodId("fy-2025")


def available(value: str) -> AvailableObservation:
    return AvailableObservation(
        period_id=PERIOD_ID,
        status=MetricStatus.AVAILABLE,
        normalized_value=Decimal(value),
    )


def test_financial_health_ratios_are_calculated_as_percentages() -> None:
    assert calculate_free_cash_flow_margin(
        available("24"), available("120")
    ).normalized_value == Decimal("20.0")
    assert calculate_debt_ratio(
        available("45"), available("100")
    ).normalized_value == Decimal("45.00")
    assert calculate_net_debt_ratio(
        available("-10"), available("100")
    ).normalized_value == Decimal("-10.0")


def test_financial_health_ratio_keeps_zero_denominator_unknown() -> None:
    result = calculate_debt_ratio(available("45"), available("0"))

    assert isinstance(result, UnavailableObservation)
    assert result.status is MetricStatus.NOT_MEANINGFUL
    assert result.reason == "zero_denominator"
    assert result.notes == ("debt_ratio",)
