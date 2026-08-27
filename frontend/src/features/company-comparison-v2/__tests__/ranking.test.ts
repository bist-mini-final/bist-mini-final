import { describe, expect, it } from 'vitest';
import { normalizedWeights, rankCompanies } from '../ranking';
import type { LeagueCompany } from '../leagueTypes';

function company(id: string, growth: number, profitability: number, stability: number): LeagueCompany {
  return {
    companyId: id, displayName: id, currency: 'KRW', scale: 'millions',
    rank: 1, previousRank: 2, rankChange: 1, compositeScore: 0, growthScore: growth,
    profitabilityScore: profitability, stabilityScore: stability, revenueCagr: 0, operatingMargin: 0,
    liabilitiesToAssets: 0, netDebt: 0, tier: 'C', candles: [],
  };
}

describe('rankCompanies', () => {
  it('changes rank according to the selected judgment basis', () => {
    const companies = [company('growth', 100, 20, 20), company('stable', 20, 20, 100)];
    expect(rankCompanies(companies, { growth: 60, profitability: 20, stability: 20 })[0].companyId).toBe('growth');
    expect(rankCompanies(companies, { growth: 20, profitability: 20, stability: 60 })[0].companyId).toBe('stable');
  });

  it('normalizes custom weights to one hundred percent', () => {
    expect(normalizedWeights({ growth: 20, profitability: 20, stability: 10 })).toEqual({ growth: 40, profitability: 40, stability: 20 });
  });
});
