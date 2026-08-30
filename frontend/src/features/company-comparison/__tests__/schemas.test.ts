import { describe, expect, it } from 'vitest';
import { parseCompanyComparisonSnapshot } from '../schemas';

function company(index: number) {
  return {
    company_id: `company-${index}`,
    display_name: `Company ${index}`,
    currency: 'KRW',
    scale: 'millions',
    source_snapshot_id: `snapshot-${index}`,
    historical_start_year: 2022,
    historical_end_year: 2025,
    rank: index,
    previous_rank: index,
    rank_change: 0,
    composite_score: 75,
    growth_score: 80,
    profitability_score: 70,
    stability_score: 75,
    revenue_cagr: 12,
    operating_margin: 18,
    liabilities_to_assets: 35,
    net_debt: -10,
    net_debt_to_revenue: -1,
    tier: 'A',
    periods: Array.from({ length: 7 }, (_, offset) => ({
      year: 2022 + offset,
      period_type: offset < 4 ? 'historical' : 'forecast',
      revenue: 100,
      operating_income: 18,
      operating_margin: 18,
      evidence_ids: [`E${index}`],
      assumption_id: offset < 4 ? null : 'historical-cagr-hold-v1',
    })),
  };
}

function payload() {
  return {
    schema_version: 1,
    snapshot: {
      snapshot_id: 'comparison-snapshot',
      status: 'ready',
      generated_at: '2026-08-28T00:00:00Z',
      source_fingerprint: 'a'.repeat(64),
      source_snapshot_ids: ['snapshot-1', 'snapshot-2'],
      scoring_version: 'financial-league-v3',
      forecast_version: 'historical-cagr-hold-v1',
    },
    historical_start_year: 2022,
    historical_end_year: 2025,
    forecast_end_year: 2028,
    companies: [company(1), company(2)],
    spotlight: {
      leader_company_id: 'company-1',
      riser_company_id: 'company-2',
      average_cagr: 12,
      average_margin: 18,
      average_liabilities_to_assets: 35,
      cagr_distribution: [{ label: '10-15%', count: 2 }],
      margin_distribution: [{ label: '15-20%', count: 2 }],
    },
    evidence: [1, 2].map((index) => ({
      evidence_id: `E${index}`,
      company_id: `company-${index}`,
      metric_id: 'revenue',
      year: 2025,
      file_name: 'financials.xlsx',
      sheet_name: 'Sheet1',
      cell_coord: `C${index}`,
      source_text: '원본 재무 데이터',
      origin: 'bi_snapshot',
    })),
    exclusions: [],
    assumptions: [{
      assumption_id: 'historical-cagr-hold-v1',
      description: '실제 관측 CAGR과 최근 영업이익률을 적용한 3개년 단순 예측입니다.',
    }],
  };
}

describe('parseCompanyComparisonSnapshot', () => {
  it('maps the durable snapshot contract to frontend fields', () => {
    const result = parseCompanyComparisonSnapshot(payload());
    expect(result.companies).toHaveLength(2);
    expect(result.companies[0].periods[4].periodType).toBe('forecast');
    expect(result.evidence[0].origin).toBe('bi_snapshot');
    expect(result.snapshot.sourceSnapshotIds).toHaveLength(2);
  });

  it('rejects a snapshot with fewer than two companies', () => {
    expect(() => parseCompanyComparisonSnapshot({
      ...payload(),
      companies: [company(1)],
    })).toThrow();
  });
});
