import { describe, expect, it } from 'vitest';
import {
  buildFinancialHealthHeatmap,
  classifyFinancialHealthTrend,
} from '../financialHealthHeatmap';
import { DASHBOARD_FIXTURES } from '../../../../test/fixtures/biDashboardFixtures';
import type { BiDashboardSnapshot, MetricSeries } from '../../types';

function percentSeries(
  metricId: MetricSeries['metricId'],
  label: string,
  values: readonly [string, string | null][],
): MetricSeries {
  return {
    metricId,
    label,
    valueKind: 'percent',
    currency: null,
    scale: null,
    status: values.some(([, value]) => value !== null) ? 'available' : 'missing',
    observations: values.map(([periodId, value]) => value === null ? {
      periodId,
      status: 'missing',
      rawValue: null,
      normalizedValue: null,
      evidence: [],
      notes: [],
      reason: 'not_found',
    } : {
      periodId,
      status: 'available',
      rawValue: value,
      normalizedValue: value,
      evidence: [],
      notes: [],
    }),
  };
}

describe('financial health heatmap', () => {
  it('reverses the improvement direction for debt metrics', () => {
    expect(classifyFinancialHealthTrend(9, 12, 'higher')).toBe('strong-improvement');
    expect(classifyFinancialHealthTrend(42, 39, 'lower')).toBe('strong-improvement');
    expect(classifyFinancialHealthTrend(39, 42, 'lower')).toBe('strong-decline');
    expect(classifyFinancialHealthTrend(10, 10.3, 'higher')).toBe('stable');
  });

  it('builds period cells with baseline, trend, and NA states', () => {
    const fixture = DASHBOARD_FIXTURES[0];
    const periods = fixture.periods.slice(0, 3);
    const periodValues: readonly [string, string | null][] = [
      [periods[0].periodId, '10'],
      [periods[1].periodId, '13'],
      [periods[2].periodId, null],
    ];
    const series = percentSeries('operating_margin', '영업이익률', periodValues);
    const dashboard: BiDashboardSnapshot = {
      ...fixture,
      periods,
      metrics: { ...fixture.metrics, operating_margin: series },
    };

    const model = buildFinancialHealthHeatmap(dashboard, '전체', 'L');
    const operatingMargin = model.rows.find((row) => row.metricId === 'operating_margin');

    expect(model.periods).toHaveLength(3);
    expect(operatingMargin?.cells.map((cell) => cell.trend)).toEqual([
      'baseline',
      'strong-improvement',
      'na',
    ]);
    expect(operatingMargin?.cells[1].delta).toBe(3);
    expect(operatingMargin?.cells[2].displayValue).toBe('NA');
  });
});
