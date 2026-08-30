from dataclasses import dataclass
from decimal import Decimal
from typing import Final, assert_never

from backend.domains.bi.domain.formula_dsl import FormulaEvaluationError, evaluate_formula
from backend.domains.bi.domain.models import (
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


def _calculate_formula(
    formula_id: str,
    named_inputs: tuple[tuple[str, MetricObservation], ...],
) -> MetricObservation:
    if not named_inputs:
        raise ValueError("formula requires at least one input")
    inputs = tuple(observation for _, observation in named_inputs)
    period_id = inputs[0].period_id
    blocked = _prepare_inputs(period_id, formula_id, inputs)
    if blocked is not None:
        return blocked
    values = {
        name: observation.normalized_value
        for name, observation in named_inputs
        if isinstance(observation, AvailableObservation)
    }
    if len(values) != len(inputs):
        raise TypeError("formula inputs were not narrowed to available observations")
    try:
        value = evaluate_formula(formula_id, values)
    except FormulaEvaluationError as exc:
        if str(exc) == "zero_denominator":
            return _not_meaningful(period_id, formula_id, inputs)
        raise
    return _available_result(DerivedValue(period_id, formula_id, value), inputs)


def _calculate_ratio(
    numerator_name: str,
    numerator: MetricObservation,
    denominator_name: str,
    denominator: MetricObservation,
    formula_id: str,
) -> MetricObservation:
    return _calculate_formula(
        formula_id,
        ((numerator_name, numerator), (denominator_name, denominator)),
    )


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
        case _:
            raise TypeError("growth inputs were not narrowed to available observations")


def calculate_operating_margin(
    operating_income: MetricObservation,
    revenue: MetricObservation,
) -> MetricObservation:
    return _calculate_ratio(
        "operating_income", operating_income, "revenue", revenue, "operating_margin"
    )


def calculate_net_margin(
    net_income: MetricObservation,
    revenue: MetricObservation,
) -> MetricObservation:
    return _calculate_ratio("net_income", net_income, "revenue", revenue, "net_margin")


def calculate_free_cash_flow(
    operating_cash_flow: MetricObservation,
    normalized_capex: MetricObservation,
) -> MetricObservation:
    return _calculate_formula(
        "free_cash_flow",
        (
            ("operating_cash_flow", operating_cash_flow),
            ("capital_expenditure", normalized_capex),
        ),
    )


def calculate_free_cash_flow_margin(
    free_cash_flow: MetricObservation,
    revenue: MetricObservation,
) -> MetricObservation:
    return _calculate_ratio(
        "free_cash_flow",
        free_cash_flow,
        "revenue",
        revenue,
        "free_cash_flow_margin",
    )


def calculate_debt_ratio(
    total_liabilities: MetricObservation,
    total_assets: MetricObservation,
) -> MetricObservation:
    return _calculate_ratio(
        "total_liabilities",
        total_liabilities,
        "total_assets",
        total_assets,
        "debt_ratio",
    )


def calculate_net_debt_ratio(
    net_debt: MetricObservation,
    total_assets: MetricObservation,
) -> MetricObservation:
    return _calculate_ratio(
        "net_debt", net_debt, "total_assets", total_assets, "net_debt_ratio"
    )


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
        case _:
            raise TypeError("debt inputs were not narrowed to available observations")

    inputs = components.observations()
    period_id = components.short_term_debt.period_id
    formula_id = "total_debt_components"
    avail_components = [
        obs for obs in inputs if isinstance(obs, AvailableObservation)
    ]
    if avail_components:
        st_val = (
            components.short_term_debt.normalized_value
            if isinstance(components.short_term_debt, AvailableObservation)
            else Decimal(0)
        )
        cp_val = (
            components.current_portion_of_long_term_debt.normalized_value
            if isinstance(
                components.current_portion_of_long_term_debt,
                AvailableObservation,
            )
            else Decimal(0)
        )
        lt_val = (
            components.long_term_debt.normalized_value
            if isinstance(components.long_term_debt, AvailableObservation)
            else Decimal(0)
        )
        return _available_result(
            DerivedValue(
                period_id,
                formula_id,
                st_val + cp_val + lt_val,
            ),
            inputs,
        )

    blocked = _prepare_inputs(period_id, formula_id, inputs)
    if blocked is not None:
        return blocked

    return UnavailableObservation(
        period_id=period_id,
        status=MetricStatus.MISSING,
        evidence=_merge_evidence(inputs),
        notes=(formula_id,),
        reason="no_debt_components_available",
    )


def calculate_net_debt(
    total_debt: MetricObservation,
    cash_and_short_term_investments: MetricObservation,
) -> MetricObservation:
    return _calculate_formula(
        "net_debt",
        (
            ("total_debt", total_debt),
            (
                "cash_and_short_term_investments",
                cash_and_short_term_investments,
            ),
        ),
    )
