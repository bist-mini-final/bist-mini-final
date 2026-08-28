import { describe, expect, it } from 'vitest';
import { parseFinancialLeague } from '../leagueSchema';

function company(index: number) {
  return {
    company_id: `company-${index}`, display_name: `Company ${index}`,
    currency: 'KRW', scale: 'millions', rank: index, previous_rank: index, rank_change: 0,
    composite_score: 75, growth_score: 80, profitability_score: 70, stability_score: 75,
    revenue_cagr: 12, operating_margin: 18, liabilities_to_assets: 35, net_debt: -10, tier: 'A',
    net_debt_to_revenue: -1,
    candles: Array.from({ length: 8 }, (_, offset) => ({
      year: 2021 + offset, period_type: offset < 5 ? 'historical' : 'forecast',
      open: 20, high: 30, low: 18, close: 28, revenue: 100,
      operating_income: 18, operating_margin: 18, evidence_id: `E${index}`,
    })),
  };
}

function payload() {
  return {
    schema_version: 1, generated_at: '2026-08-26T00:00:00Z', historical_end_year: 2025,
    companies: Array.from({ length: 15 }, (_, index) => company(index + 1)),
    spotlight: {
      leader_company_id: 'company-1', riser_company_id: 'company-2', average_cagr: 12,
      average_margin: 18, cagr_distribution: [{ label: '10-15%', count: 15 }],
      margin_distribution: [{ label: '15-20%', count: 15 }],
    },
    evidence: Array.from({ length: 15 }, (_, index) => ({
      evidence_id: `E${index + 1}`, company_id: `company-${index + 1}`, file_name: 'financials.xlsx',
      sheet_name: 'Sheet1', cell_coord: `C${index + 1}`, source_text: '원본 재무 데이터', origin: 'snapshot',
    })),
  };
}

describe('parseFinancialLeague', () => {
  it('maps the league API contract to frontend fields', () => {
    const result = parseFinancialLeague(payload());
    expect(result.companies).toHaveLength(15);
    expect(result.companies[0].candles[5].periodType).toBe('forecast');
    expect(result.evidence[0].cellCoord).toBe('C1');
  });

  it('rejects an undersized scenario universe', () => {
    expect(() => parseFinancialLeague({ ...payload(), companies: [company(1)] })).toThrow();
  });
});
