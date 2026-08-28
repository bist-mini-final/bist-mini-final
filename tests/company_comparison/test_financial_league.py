from collections import Counter
from math import isfinite

from backend.features.bi.models import AmountScale, BiEvidence, CompanyId
from backend.features.company_comparison.league_service import (
    BaseFinancials,
    FinancialLeagueService,
    composite_tier,
    financial_stability_score,
    growth_score,
    profitability_score,
)
from backend.features.company_comparison.models import FinancialTier


class UnavailableStore:
    def list_companies(self):
        raise AttributeError("database is unavailable")

    def get_current(self, company_id):
        return None


class FixtureLeagueService(FinancialLeagueService):
    def __init__(self, count: int = 18) -> None:
        super().__init__(UnavailableStore())
        self._bases = tuple(_base(index) for index in range(1, count + 1))

    def _load_bases(self) -> tuple[BaseFinancials, ...]:
        return self._bases


def _base(index: int) -> BaseFinancials:
    growth = 0.035 + index * 0.004
    revenue_2021 = 500.0 + index * 45
    return BaseFinancials(
        company_id=CompanyId(f"company-{index}"),
        display_name=f"Company {index}",
        currency="KRW",
        scale=AmountScale.MILLIONS,
        revenues={year: revenue_2021 * pow(1 + growth, year - 2021) for year in range(2021, 2026)},
        margins={year: 8.0 + index * 0.55 for year in range(2021, 2026)},
        liabilities_to_assets=28.0 + index,
        net_debt=80.0 - index * 9,
        file_name=f"company-{index}.xlsm",
        evidence=BiEvidence(
            cell_id=f"company-{index}-revenue-2025",
            sheet_name="Key_Stats",
            cell_coord="I33",
            source_text=f"Company {index} 2025 revenue",
        ),
    )


def test_league_ranks_each_loaded_company_once() -> None:
    result = FixtureLeagueService().build()

    assert len(result.companies) == 18
    assert [company.rank for company in result.companies] == list(range(1, 19))
    assert {company.company_id for company in result.companies} == {
        f"company-{index}" for index in range(1, 19)
    }
    assert all("·" not in company.display_name for company in result.companies)
    assert all(0 <= company.composite_score <= 100 for company in result.companies)
    assert all(len(company.candles) == 8 for company in result.companies)
    assert sum(bucket.count for bucket in result.spotlight.cagr_distribution) == 18
    assert result.companies[0].company_id == result.spotlight.leader_company_id


def test_league_exposes_only_fifteen_page_scoped_temporary_companies_without_store() -> None:
    result = FinancialLeagueService(UnavailableStore()).build()

    assert len(result.companies) == 15
    assert all(company.company_id.startswith("temp-") for company in result.companies)
    assert {item.file_name for item in result.evidence} == {"company-comparison-temporary-data"}


def test_temporary_companies_have_balanced_composite_grades() -> None:
    result = FinancialLeagueService(UnavailableStore()).build()

    assert Counter(company.tier for company in result.companies) == {
        FinancialTier.S: 3,
        FinancialTier.A: 4,
        FinancialTier.B: 5,
        FinancialTier.C: 3,
    }
    assert all(
        company.tier == composite_tier(company.composite_score) for company in result.companies
    )
    assert all(
        isfinite(value)
        for company in result.companies
        for value in (
            company.composite_score,
            company.stability_score,
            company.net_debt_to_revenue,
            company.revenue_cagr,
            company.operating_margin,
        )
    )


def _anchor_composite(
    revenue_2021: float,
    revenue_2025: float,
    margin: float,
    liabilities_to_assets: float,
    net_debt: float,
) -> float:
    cagr = (pow(revenue_2025 / revenue_2021, 1 / 4) - 1) * 100
    return round(
        growth_score(cagr) * 0.35
        + profitability_score(margin) * 0.35
        + financial_stability_score(liabilities_to_assets, net_debt, revenue_2025) * 0.30,
        2,
    )


def test_parsed_anchor_profiles_calibrate_the_absolute_score_scale() -> None:
    bistelligence = _anchor_composite(12_000, 18_000, 14.5, 37.60, -1_800)
    coldplay = _anchor_composite(15_600, 17_700, 10.197740112994351, 49.43, -354)
    dh_innovation = _anchor_composite(17_400, 12_400, -3.0, 100.0, 3_968)

    assert bistelligence == 93.02
    assert composite_tier(bistelligence) == FinancialTier.S
    assert coldplay == 67.41
    assert composite_tier(coldplay) == FinancialTier.B
    assert dh_innovation == 6.49
    assert composite_tier(dh_innovation) == FinancialTier.C

    virtual_companies = FinancialLeagueService(UnavailableStore()).build().companies
    assert max(company.composite_score for company in virtual_companies) > bistelligence


def test_overall_tier_uses_the_standard_one_hundred_point_scale() -> None:
    assert composite_tier(90) == FinancialTier.S
    assert composite_tier(75) == FinancialTier.A
    assert composite_tier(50) == FinancialTier.B
    assert composite_tier(49.99) == FinancialTier.C


def test_league_score_uses_documented_weights_and_valid_candles() -> None:
    result = FixtureLeagueService().build()

    for company in result.companies:
        expected = (
            company.growth_score * 0.35
            + company.profitability_score * 0.35
            + company.stability_score * 0.30
        )
        assert company.composite_score == round(expected, 2)
        for candle in company.candles:
            assert candle.low <= min(candle.open, candle.close)
            assert candle.high >= max(candle.open, candle.close)
            assert candle.period_type == ("historical" if candle.year <= 2025 else "forecast")


def test_league_preserves_excel_evidence_coordinates() -> None:
    result = FixtureLeagueService().build()

    evidence_ids = {item.evidence_id for item in result.evidence}
    assert len(evidence_ids) == 18
    assert all(
        candle.evidence_id in evidence_ids
        for company in result.companies
        for candle in company.candles
    )
    assert all(item.sheet_name and item.cell_coord and item.source_text for item in result.evidence)
