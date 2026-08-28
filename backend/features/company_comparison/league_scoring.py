from __future__ import annotations

from typing import Final

from .models import FinancialTier

# Absolute 100-point benchmarks calibrated from the parsed anchor profiles.
# They remain fixed when companies enter or leave the league.
GROWTH_SCORE_FLOOR: Final = -10.0
GROWTH_SCORE_CEILING: Final = 12.0
MARGIN_SCORE_FLOOR: Final = -5.0
MARGIN_SCORE_CEILING: Final = 15.0
COMPOSITE_TIER_THRESHOLDS: Final = {
    FinancialTier.S: 90.0,
    FinancialTier.A: 75.0,
    FinancialTier.B: 50.0,
    FinancialTier.C: 0.0,
}


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _benchmark_score(value: float, floor: float, ceiling: float) -> float:
    return _clamp((value - floor) / (ceiling - floor) * 100.0)


def growth_score(growth_percent: float) -> float:
    return round(
        _benchmark_score(growth_percent, GROWTH_SCORE_FLOOR, GROWTH_SCORE_CEILING),
        2,
    )


def profitability_score(margin_percent: float) -> float:
    return round(
        _benchmark_score(margin_percent, MARGIN_SCORE_FLOOR, MARGIN_SCORE_CEILING),
        2,
    )


def financial_stability_score(
    liabilities_to_assets: float,
    net_debt: float,
    annual_revenue: float,
) -> float:
    """Score resilience from leverage and net debt relative to annual revenue."""
    leverage_score = _clamp((70.0 - liabilities_to_assets) / 40.0 * 100.0)
    net_debt_ratio = net_debt / max(annual_revenue, 1.0) * 100.0
    funding_score = 100.0 if net_debt_ratio <= 0 else _clamp(100.0 - net_debt_ratio * 4.0)
    return round(leverage_score * 0.70 + funding_score * 0.30, 2)


def composite_tier(score: float) -> FinancialTier:
    if score >= COMPOSITE_TIER_THRESHOLDS[FinancialTier.S]:
        return FinancialTier.S
    if score >= COMPOSITE_TIER_THRESHOLDS[FinancialTier.A]:
        return FinancialTier.A
    if score >= COMPOSITE_TIER_THRESHOLDS[FinancialTier.B]:
        return FinancialTier.B
    return FinancialTier.C


__all__ = [
    "COMPOSITE_TIER_THRESHOLDS",
    "GROWTH_SCORE_CEILING",
    "GROWTH_SCORE_FLOOR",
    "MARGIN_SCORE_CEILING",
    "MARGIN_SCORE_FLOOR",
    "composite_tier",
    "financial_stability_score",
    "growth_score",
    "profitability_score",
]
