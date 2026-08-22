import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { DASHBOARD_FIXTURES } from '../../fixtures/dashboardFixtures';
import type { BiDashboardSnapshot, MetricId, MetricSeries } from '../../types';
import { StabilityChart } from '../charts/StabilityChart';

const STABILITY_METRICS = [
  'cash_and_short_term_investments',
  'total_debt',
  'net_debt',
] as const satisfies readonly MetricId[];

function withMissingLatestStabilityValues(): BiDashboardSnapshot {
  const dashboard = DASHBOARD_FIXTURES[0];
  const latestPeriodId = dashboard.periods[dashboard.periods.length - 1]?.periodId;
  const metrics = { ...dashboard.metrics };

  for (const metricId of STABILITY_METRICS) {
    const series = dashboard.metrics[metricId];
    if (!series || !latestPeriodId) continue;
    metrics[metricId] = {
      ...series,
      observations: series.observations.map((observation) => observation.periodId === latestPeriodId
        ? {
            periodId: observation.periodId,
            status: 'missing',
            normalizedValue: null,
            rawValue: null,
            evidence: [],
            notes: [],
            reason: '최신 기간 값 없음',
          }
        : observation),
    } satisfies MetricSeries;
  }

  return { ...dashboard, metrics };
}

describe('StabilityChart', () => {
  it('keeps missing latest values as missing instead of displaying zero', () => {
    render(<StabilityChart dashboard={withMissingLatestStabilityValues()} range="최근 5개" size="M" />);

    const visual = screen.getByRole('img', { name: /현금·차입금 균형/ });
    expect(within(visual).getAllByText('데이터 없음')).toHaveLength(3);
    expect(screen.queryByText('0백만원')).not.toBeInTheDocument();
  });
});
