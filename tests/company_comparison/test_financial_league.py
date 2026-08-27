import pytest

from backend.features.bi.models import AmountScale, BiEvidence, CompanyId
from backend.features.company_comparison.calculator import ComparisonDataError
from backend.features.company_comparison.league_service import (
    BaseFinancials,
    FinancialLeagueService,
)


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
        revenues={
            year: revenue_2021 * pow(1 + growth, year - 2021)
            for year in range(2021, 2026)
        },
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


def test_league_requires_loaded_company_data_instead_of_fallbacks() -> None:
    with pytest.raises(ComparisonDataError) as error:
        FinancialLeagueService(UnavailableStore()).build()

    assert error.value.code == "financial_league_insufficient_companies"


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
            assert candle.period_type == (
                "historical" if candle.year <= 2025 else "forecast"
            )


def test_league_preserves_excel_evidence_coordinates() -> None:
    result = FixtureLeagueService().build()

    evidence_ids = {item.evidence_id for item in result.evidence}
    assert len(evidence_ids) == 18
    assert all(
        candle.evidence_id in evidence_ids
        for company in result.companies
        for candle in company.candles
    )
    assert all(
        item.sheet_name and item.cell_coord and item.source_text
        for item in result.evidence
    )
