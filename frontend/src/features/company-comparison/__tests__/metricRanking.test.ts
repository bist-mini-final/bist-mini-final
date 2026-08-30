import { describe, expect, it } from 'vitest';
import {
  orderForDisplay,
  rankCompaniesByComposite,
  rankCompaniesByMetric,
  toggleCompanySelection,
} from '../metricRanking';
import type { ComparisonCompany } from '../types';

function company(
  id: string,
  revenue: number,
  operatingIncome: number,
  cagr: number,
  margin: number,
  compositeScore: number,
): ComparisonCompany {
  return {
    companyId: id, displayName: id, currency: 'KRW', scale: 'millions',
    sourceSnapshotId: `snapshot-${id}`,
    historicalStartYear: 2025, historicalEndYear: 2025,
    rank: 1, previousRank: 1, rankChange: 0, compositeScore,
    growthScore: 50, profitabilityScore: 50, stabilityScore: 50,
    revenueCagr: cagr, operatingMargin: margin, liabilitiesToAssets: 40,
    netDebt: 0, netDebtToRevenue: 0, tier: 'B',
    periods: [{
      year: 2025, periodType: 'historical', revenue, operatingIncome,
      operatingMargin: margin, evidenceIds: ['E1'], assumptionId: null,
    }, {
      year: 2026, periodType: 'forecast', revenue, operatingIncome,
      operatingMargin: margin, evidenceIds: ['E1'], assumptionId: 'forecast-v1',
    }, {
      year: 2027, periodType: 'forecast', revenue, operatingIncome,
      operatingMargin: margin, evidenceIds: ['E1'], assumptionId: 'forecast-v1',
    }, {
      year: 2028, periodType: 'forecast', revenue, operatingIncome,
      operatingMargin: margin, evidenceIds: ['E1'], assumptionId: 'forecast-v1',
    }],
  };
}

const companies = [
  { ...company('alpha', 100, 15, 8, 15, 70), rank: 3 },
  { ...company('beta', 200, 10, 12, 5, 90), rank: 1 },
  { ...company('gamma', 150, 30, 8, 20, 80), rank: 2 },
];

describe('composite ranking and display sorting', () => {
  it('assigns the official rank only from composite score', () => {
    expect(rankCompaniesByComposite(companies).map((item) => item.company.companyId))
      .toEqual(['beta', 'gamma', 'alpha']);
  });

  it('uses competition ranking for equal composite scores', () => {
    const tied = [
      { ...companies[0], rank: 2 },
      { ...companies[1], rank: 2, compositeScore: 70 },
      { ...companies[2], rank: 1 },
    ];
    expect(rankCompaniesByComposite(tied).map((item) => item.rank)).toEqual([1, 2, 2]);
  });

  it('assigns metric-specific ranks for the active ranking column', () => {
    const byRevenue = rankCompaniesByMetric(companies, 'revenue');
    expect(byRevenue.map((item) => [item.company.companyId, item.rank]))
      .toEqual([['beta', 1], ['gamma', 2], ['alpha', 3]]);
  });

  it('shares a rank when the active metric values are equal', () => {
    const byGrowth = rankCompaniesByMetric(companies, 'revenueCagr');
    expect(byGrowth.map((item) => [item.company.companyId, item.rank]))
      .toEqual([['beta', 1], ['alpha', 2], ['gamma', 2]]);
  });

  it('sorts a detail column without changing official composite ranks', () => {
    const official = rankCompaniesByComposite(companies);
    const byOperatingIncome = orderForDisplay(official, 'operatingIncome', 'best-first');
    expect(byOperatingIncome.map((item) => [item.company.companyId, item.rank]))
      .toEqual([['gamma', 2], ['alpha', 3], ['beta', 1]]);
  });

  it('reverses display order while preserving official ranks', () => {
    const reversed = orderForDisplay(
      rankCompaniesByComposite(companies), 'revenue', 'worst-first',
    );
    expect(reversed.map((item) => item.rank)).toEqual([3, 2, 1]);
  });
});

describe('toggleCompanySelection', () => {
  it('keeps two selected companies independently from ranking state', () => {
    const selected = toggleCompanySelection(toggleCompanySelection(new Set(), 'alpha'), 'beta');
    expect([...selected]).toEqual(['alpha', 'beta']);
    expect([...toggleCompanySelection(selected, 'gamma')]).toEqual(['beta', 'gamma']);
  });
});
