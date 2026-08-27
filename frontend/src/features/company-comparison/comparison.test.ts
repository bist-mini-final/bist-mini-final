import { describe, expect, it } from 'vitest';
import { DASHBOARD_FIXTURES } from '../../test/fixtures/biDashboardFixtures';
import type { BiDashboardSnapshot, MetricId, MetricSeries } from '../bi/types';
import {
  buildComparisonViewModel,
  getCommonFiscalYears,
  presentNetDebt,
  type ComparisonDashboard,
  type ComparisonCompanyKey,
} from './comparison';

interface CompanySeed {
  readonly key: ComparisonCompanyKey;
  readonly label: string;
  readonly color: string;
  readonly revenue: readonly number[];
  readonly operatingIncome: readonly number[];
  readonly operatingMargin: readonly number[];
  readonly totalLiabilities: readonly number[];
  readonly totalAssets: readonly number[];
  readonly netDebt: readonly number[];
}

function replaceSeries(series: MetricSeries, values: readonly number[]): MetricSeries {
  return {
    ...series,
    observations: series.observations.map((observation, index) => observation.status === 'available'
      ? { ...observation, normalizedValue: String(values[index] ?? values[values.length - 1]) }
      : observation),
  };
}

function dashboardFromSeed(seed: CompanySeed): ComparisonDashboard {
  const base = DASHBOARD_FIXTURES[0];
  const replacements: Readonly<Partial<Record<MetricId, readonly number[]>>> = {
    revenue: seed.revenue,
    operating_income: seed.operatingIncome,
    operating_margin: seed.operatingMargin,
    total_liabilities: seed.totalLiabilities,
    total_assets: seed.totalAssets,
    net_debt: seed.netDebt,
  };
  const metrics = Object.fromEntries(Object.entries(base.metrics).map(([metricId, series]) => {
    const values = replacements[metricId as MetricId];
    return [metricId, values && series ? replaceSeries(series, values) : series];
  })) as BiDashboardSnapshot['metrics'];
  return {
    key: seed.key,
    label: seed.label,
    color: seed.color,
    dashboard: {
      ...base,
      company: { companyId: seed.key, displayName: seed.label },
      source: { ...base.source, fileName: `${seed.key}.xlsx` },
      metrics,
    },
  };
}

const COMPANIES = [
  dashboardFromSeed({
    key: 'bistelligence', label: 'Bistelligence', color: '#6d3bd1',
    revenue: [100, 110, 121, 133.1, 146.41, 150], operatingIncome: [10, 12, 14, 16, 18, 19],
    operatingMargin: [10, 11, 12, 13, 14, 14], totalLiabilities: [40, 40, 40, 40, 40, 40],
    totalAssets: [100, 100, 100, 100, 100, 100], netDebt: [-10, -10, -10, -10, -10, -10],
  }),
  dashboardFromSeed({
    key: 'coldplay', label: 'Coldplay', color: '#1677d2',
    revenue: [100, 105, 110, 115, 120, 124], operatingIncome: [9, 10, 11, 12, 13, 14],
    operatingMargin: [9, 9.5, 10, 10.5, 11, 11], totalLiabilities: [55, 55, 55, 55, 55, 55],
    totalAssets: [100, 100, 100, 100, 100, 100], netDebt: [20, 20, 20, 20, 20, 20],
  }),
  dashboardFromSeed({
    key: 'dh-innovation', label: 'DH Innovation', color: '#ed8a0a',
    revenue: [100, 90, 80, 70, 60, 58], operatingIncome: [8, 6, 4, 2, -2, -3],
    operatingMargin: [8, 6, 4, 2, -3, -4], totalLiabilities: [90, 90, 90, 90, 90, 90],
    totalAssets: [100, 100, 100, 100, 100, 100], netDebt: [80, 80, 80, 80, 80, 80],
  }),
] as const;

describe('company comparison model', () => {
  it('uses only fiscal years shared by all three dashboards', () => {
    expect(getCommonFiscalYears(COMPANIES)).toEqual([2021, 2022, 2023, 2024, 2025]);
  });

  it('recalculates every period-derived value when the start year changes', () => {
    const full = buildComparisonViewModel(COMPANIES, 2021, 2025);
    const recent = buildComparisonViewModel(COMPANIES, 2023, 2025);
    expect(full.companies[0].revenueCagr).toBeCloseTo(10, 5);
    expect(recent.companies[0].revenueCagr).toBeCloseTo(10, 5);
    expect(full.companies[1].revenueCagr).not.toBeCloseTo(recent.companies[1].revenueCagr, 3);
    expect(recent.companies[0].points).toHaveLength(3);
    expect(recent.insights[0].body).toContain('2023–2025');
    expect(recent.evidenceRows[0].basis).toBe('2023–2025 연간');
  });

  it('links each comparison brief to verified evidence rows', () => {
    const model = buildComparisonViewModel(COMPANIES, 2021, 2025);
    expect(model.insights[0].body).toContain('Bistelligence');
    expect(model.insights.map((insight) => insight.evidenceIds)).toEqual([[1], [2], [3, 4]]);
    expect(model.evidenceRows.every((row) => row.verified && row.evidence.length > 0)).toBe(true);
  });

  it('presents negative net debt as positive net cash without changing the source value', () => {
    const model = buildComparisonViewModel(COMPANIES, 2021, 2025);
    expect(model.companies[0].netDebt).toBe(-10);
    expect(presentNetDebt(model.companies[0].netDebt)).toEqual({
      label: '순현금',
      value: 10,
      description: '현금성 자산이 총차입금보다 많습니다.',
    });
    expect(presentNetDebt(3968)).toMatchObject({ label: '순부채', value: 3968 });
    expect(presentNetDebt(0)).toMatchObject({ label: '순부채', value: 0 });
  });

  it('rebuilds metrics, brief, and evidence for only the two selected companies', () => {
    const model = buildComparisonViewModel([COMPANIES[1], COMPANIES[2]], 2021, 2025);
    expect(model.companies.map((company) => company.label)).toEqual(['Coldplay', 'DH Innovation']);
    expect(model.insights[0].body).toContain('Coldplay');
    expect(model.insights[0].body).toContain('2개 비교 기업의');
    expect(model.insights.map((insight) => insight.body).join(' ')).not.toContain('Bistelligence');
    expect(model.insights[1].body).toContain('2개 비교 기업 중');
    expect(model.evidenceRows.every((row) => row.sources.length === 2)).toBe(true);
  });
});
