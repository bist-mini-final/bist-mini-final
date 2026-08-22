from decimal import Decimal
import unittest

from backend.bi.calculator import (
    DebtComponents,
    calculate_free_cash_flow,
    calculate_net_debt,
    calculate_net_margin,
    calculate_operating_margin,
    calculate_revenue_yoy_growth,
    calculate_total_debt,
)
from backend.bi.models import (
    AvailableObservation,
    BiEvidence,
    MetricObservation,
    MetricStatus,
    UnavailableObservation,
)


def available(period_id: str, value: str, cell_coord: str) -> AvailableObservation:
    return AvailableObservation(
        period_id=period_id,
        status=MetricStatus.AVAILABLE,
        raw_value=value,
        normalized_value=Decimal(value),
        evidence=(
            BiEvidence(
                cell_id=f"sheet:{cell_coord}",
                sheet_name="Sheet",
                cell_coord=cell_coord,
                source_text=value,
            ),
        ),
    )


def unavailable(
    status: MetricStatus,
    reason: str,
    period_id: str = "fy-2025",
) -> UnavailableObservation:
    return UnavailableObservation(
        period_id=period_id,
        status=status,
        reason=reason,
    )


class CalculatorTests(unittest.TestCase):
    def test_revenue_growth_uses_decimal_formula(self) -> None:
        # Given
        current = available("fy-2025", "125", "B12")
        previous = available("fy-2024", "100", "C12")

        # When
        result = calculate_revenue_yoy_growth(current, previous)

        # Then
        self.assertEqual(result.normalized_value, Decimal("25.00"))

    def test_revenue_growth_is_not_meaningful_when_previous_is_zero(self) -> None:
        # Given
        current = available("fy-2025", "125", "B12")
        previous = available("fy-2024", "0", "C12")

        # When
        result = calculate_revenue_yoy_growth(current, previous)

        # Then
        self.assertEqual(result.status, MetricStatus.NOT_MEANINGFUL)

    def test_operating_margin_uses_percent_point_value(self) -> None:
        # Given
        operating_income = available("fy-2025", "20", "B15")
        revenue = available("fy-2025", "100", "B12")

        # When
        result = calculate_operating_margin(operating_income, revenue)

        # Then
        self.assertEqual(result.normalized_value, Decimal("20.0"))

    def test_net_margin_preserves_negative_result(self) -> None:
        # Given
        net_income = available("fy-2025", "-5", "B20")
        revenue = available("fy-2025", "100", "B12")

        # When
        result = calculate_net_margin(net_income, revenue)

        # Then
        self.assertEqual(result.normalized_value, Decimal("-5.00"))

    def test_free_cash_flow_adds_normalized_negative_capex(self) -> None:
        # Given
        operating_cash_flow = available("fy-2025", "80", "B30")
        normalized_capex = available("fy-2025", "-30", "B31")

        # When
        result = calculate_free_cash_flow(operating_cash_flow, normalized_capex)

        # Then
        self.assertEqual(result.normalized_value, Decimal("50"))

    def test_free_cash_flow_propagates_ambiguous_capex(self) -> None:
        # Given
        operating_cash_flow = available("fy-2025", "80", "B30")
        ambiguous_capex = unavailable(MetricStatus.AMBIGUOUS, "capex_sign_ambiguous")

        # When
        result = calculate_free_cash_flow(operating_cash_flow, ambiguous_capex)

        # Then
        self.assertEqual(result.status, MetricStatus.AMBIGUOUS)

    def test_total_debt_prefers_direct_value(self) -> None:
        # Given
        direct = available("fy-2025", "90", "B40")
        components = DebtComponents(
            short_term_debt=available("fy-2025", "10", "B41"),
            current_portion_of_long_term_debt=available("fy-2025", "5", "B42"),
            long_term_debt=available("fy-2025", "40", "B43"),
        )

        # When
        result = calculate_total_debt(direct, components)

        # Then
        self.assertEqual(result, direct)

    def test_total_debt_uses_components_when_direct_value_is_missing(self) -> None:
        # Given
        direct = unavailable(MetricStatus.MISSING, "direct_total_debt_missing")
        components = DebtComponents(
            short_term_debt=available("fy-2025", "10", "B41"),
            current_portion_of_long_term_debt=available("fy-2025", "5", "B42"),
            long_term_debt=available("fy-2025", "40", "B43"),
        )

        # When
        result = calculate_total_debt(direct, components)

        # Then
        self.assertEqual(result.normalized_value, Decimal("55"))

    def test_total_debt_does_not_override_ambiguous_direct_value(self) -> None:
        # Given
        direct = unavailable(MetricStatus.AMBIGUOUS, "direct_total_debt_ambiguous")
        components = DebtComponents(
            short_term_debt=available("fy-2025", "10", "B41"),
            current_portion_of_long_term_debt=available("fy-2025", "5", "B42"),
            long_term_debt=available("fy-2025", "40", "B43"),
        )

        # When
        result = calculate_total_debt(direct, components)

        # Then
        self.assertEqual(result.status, MetricStatus.AMBIGUOUS)

    def test_net_debt_can_be_negative(self) -> None:
        # Given
        total_debt = available("fy-2025", "80", "B40")
        cash = available("fy-2025", "100", "B45")

        # When
        result = calculate_net_debt(total_debt, cash)

        # Then
        self.assertEqual(result.normalized_value, Decimal("-20"))

    def test_invalid_input_has_priority_over_missing_input(self) -> None:
        # Given
        invalid_income = unavailable(MetricStatus.INVALID, "invalid_number")
        missing_revenue = unavailable(MetricStatus.MISSING, "revenue_missing")

        # When
        result = calculate_net_margin(invalid_income, missing_revenue)

        # Then
        self.assertEqual(result.status, MetricStatus.INVALID)

    def test_same_period_formula_rejects_period_mismatch(self) -> None:
        # Given
        operating_income = available("fy-2025", "20", "B15")
        revenue = available("fy-2024", "100", "C12")

        # When
        result = calculate_operating_margin(operating_income, revenue)

        # Then
        self.assertEqual(result.status, MetricStatus.INVALID)

    def test_derived_value_has_no_raw_source_value(self) -> None:
        # Given
        operating_income = available("fy-2025", "20", "B15")
        revenue = available("fy-2025", "100", "B12")

        # When
        result: MetricObservation = calculate_operating_margin(operating_income, revenue)

        # Then
        self.assertIsNone(result.raw_value)


if __name__ == "__main__":
    unittest.main()
