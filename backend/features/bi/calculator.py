from dataclasses import dataclass
from decimal import Decimal
from typing import Final, assert_never

from .models import (
    AvailableObservation,
    BiEvidence,
    MetricObservation,
    MetricStatus,
    PeriodId,
    UnavailableObservation,
)


HUNDRED: Final = Decimal("100")
UNAVAILABLE_PRIORITY: Final = (
    MetricStatus.INVALID,
    MetricStatus.AMBIGUOUS,
    MetricStatus.MISSING,
    MetricStatus.NOT_MEANINGFUL,
)


@dataclass(frozen=True, slots=True)
class DebtComponents:
    short_term_debt: MetricObservation
    current_portion_of_long_term_debt: MetricObservation
    long_term_debt: MetricObservation

    def observations(self) -> tuple[MetricObservation, ...]:
        return (
            self.short_term_debt,
            self.current_portion_of_long_term_debt,
            self.long_term_debt,
        )


@dataclass(frozen=True, slots=True)
class DerivedValue:
    period_id: PeriodId
    formula_id: str
    normalized_value: Decimal


def _merge_evidence(
    inputs: tuple[MetricObservation, ...],
) -> tuple[BiEvidence, ...]:
    evidence_by_cell: dict[str, BiEvidence] = {}
    for observation in inputs:
        for evidence in observation.evidence:
            evidence_by_cell.setdefault(evidence.cell_id, evidence)
    return tuple(evidence_by_cell.values())


def _unavailable_inputs(
    inputs: tuple[MetricObservation, ...],
) -> tuple[UnavailableObservation, ...]:
    unavailable: list[UnavailableObservation] = []
    for observation in inputs:
        match observation:
            case AvailableObservation():
                continue
            case UnavailableObservation() as blocked:
                unavailable.append(blocked)
            case unreachable:
                assert_never(unreachable)
    return tuple(unavailable)


def _prepare_inputs(
    period_id: PeriodId,
    formula_id: str,
    inputs: tuple[MetricObservation, ...],
) -> UnavailableObservation | None:
    if any(observation.period_id != period_id for observation in inputs):
        return UnavailableObservation(
            period_id=period_id,
            status=MetricStatus.INVALID,
            evidence=_merge_evidence(inputs),
            notes=(formula_id,),
            reason="period_mismatch",
        )

    unavailable = _unavailable_inputs(inputs)
    for status in UNAVAILABLE_PRIORITY:
        matching = tuple(item for item in unavailable if item.status is status)
        if matching:
            return UnavailableObservation(
                period_id=period_id,
                status=status,
                evidence=_merge_evidence(inputs),
                notes=(formula_id,),
                reason=f"input_{status.value}",
            )
    return None


def _available_result(
    value: DerivedValue,
    inputs: tuple[MetricObservation, ...],
) -> AvailableObservation:
    return AvailableObservation(
        period_id=value.period_id,
        status=MetricStatus.AVAILABLE,
        normalized_value=value.normalized_value,
        evidence=_merge_evidence(inputs),
        notes=(value.formula_id,),
    )


def _not_meaningful(
    period_id: PeriodId,
    formula_id: str,
    inputs: tuple[MetricObservation, ...],
) -> UnavailableObservation:
    return UnavailableObservation(
        period_id=period_id,
        status=MetricStatus.NOT_MEANINGFUL,
        evidence=_merge_evidence(inputs),
        notes=(formula_id,),
        reason="zero_denominator",
    )


def _calculate_ratio(
    numerator: MetricObservation,
    denominator: MetricObservation,
    formula_id: str,
) -> MetricObservation:
    inputs = (numerator, denominator)
    blocked = _prepare_inputs(numerator.period_id, formula_id, inputs)
    if blocked is not None:
        return blocked

    match numerator, denominator:
        case AvailableObservation(normalized_value=numerator_value), AvailableObservation(
            normalized_value=denominator_value
        ):
            if denominator_value == 0:
                return _not_meaningful(numerator.period_id, formula_id, inputs)
            return _available_result(
                DerivedValue(
                    numerator.period_id,
                    formula_id,
                    numerator_value / denominator_value * HUNDRED,
                ),
                inputs,
            )
        case unreachable:
            assert_never(unreachable)


def calculate_revenue_yoy_growth(
    current_revenue: MetricObservation,
    previous_revenue: MetricObservation,
) -> MetricObservation:
    formula_id = "revenue_yoy_growth"
    inputs = (current_revenue, previous_revenue)
    unavailable = _unavailable_inputs(inputs)
    for status in UNAVAILABLE_PRIORITY:
        matching = tuple(item for item in unavailable if item.status is status)
        if matching:
            return UnavailableObservation(
                period_id=current_revenue.period_id,
                status=status,
                evidence=_merge_evidence(inputs),
                notes=(formula_id,),
                reason=f"input_{status.value}",
            )

    match current_revenue, previous_revenue:
        case AvailableObservation(normalized_value=current), AvailableObservation(
            normalized_value=previous
        ):
            if previous == 0:
                return _not_meaningful(current_revenue.period_id, formula_id, inputs)
            return _available_result(
                DerivedValue(
                    current_revenue.period_id,
                    formula_id,
                    (current / previous - Decimal(1)) * HUNDRED,
                ),
                inputs,
            )
        case unreachable:
            assert_never(unreachable)


def calculate_operating_margin(
    operating_income: MetricObservation,
    revenue: MetricObservation,
) -> MetricObservation:
    return _calculate_ratio(operating_income, revenue, "operating_margin")


def calculate_net_margin(
    net_income: MetricObservation,
    revenue: MetricObservation,
) -> MetricObservation:
    return _calculate_ratio(net_income, revenue, "net_margin")


def calculate_free_cash_flow(
    operating_cash_flow: MetricObservation,
    normalized_capex: MetricObservation,
) -> MetricObservation:
    formula_id = "free_cash_flow"
    inputs = (operating_cash_flow, normalized_capex)
    blocked = _prepare_inputs(operating_cash_flow.period_id, formula_id, inputs)
    if blocked is not None:
        return blocked

    match operating_cash_flow, normalized_capex:
        case AvailableObservation(normalized_value=cash_flow), AvailableObservation(
            normalized_value=capex
        ):
            return _available_result(
                DerivedValue(
                    operating_cash_flow.period_id,
                    formula_id,
                    cash_flow + capex,
                ),
                inputs,
            )
        case unreachable:
            assert_never(unreachable)


def calculate_total_debt(
    direct_total_debt: MetricObservation | None,
    components: DebtComponents,
) -> MetricObservation:
    match direct_total_debt:
        case AvailableObservation() as available:
            return available
        case UnavailableObservation(status=MetricStatus.MISSING):
            pass
        case UnavailableObservation() as unavailable:
            return unavailable
        case None:
            pass
        case unreachable:
            assert_never(unreachable)

    inputs = components.observations()
    period_id = components.short_term_debt.period_id
    formula_id = "total_debt_components"
    blocked = _prepare_inputs(period_id, formula_id, inputs)
    if blocked is not None:
        return blocked

    match inputs:
        case (
            AvailableObservation(normalized_value=short_term),
            AvailableObservation(normalized_value=current_portion),
            AvailableObservation(normalized_value=long_term),
        ):
            return _available_result(
                DerivedValue(
                    period_id,
                    formula_id,
                    short_term + current_portion + long_term,
                ),
                inputs,
            )
        case unreachable:
            assert_never(unreachable)


def calculate_net_debt(
    total_debt: MetricObservation,
    cash_and_short_term_investments: MetricObservation,
) -> MetricObservation:
    formula_id = "net_debt"
    inputs = (total_debt, cash_and_short_term_investments)
    blocked = _prepare_inputs(total_debt.period_id, formula_id, inputs)
    if blocked is not None:
        return blocked

    match total_debt, cash_and_short_term_investments:
        case AvailableObservation(normalized_value=debt), AvailableObservation(
            normalized_value=cash
        ):
            return _available_result(
                DerivedValue(total_debt.period_id, formula_id, debt - cash),
                inputs,
            )
        case unreachable:
            assert_never(unreachable)
