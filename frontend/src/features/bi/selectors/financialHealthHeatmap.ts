import type {
  BiDashboardSnapshot,
  CardSize,
  MetricId,
  MetricObservation,
  PeriodRange,
} from '../types';
import { formatMetricValue } from './formatMetric';
import { selectPeriods } from './periods';

export type FinancialHealthTrend =
  | 'baseline'
  | 'strong-improvement'
  | 'improvement'
  | 'stable'
  | 'decline'
  | 'strong-decline'
  | 'na';

type ImprovementDirection = 'higher' | 'lower';

interface FinancialHealthMetricDefinition {
  readonly metricId: MetricId;
  readonly fallbackLabel: string;
  readonly direction: ImprovementDirection;
}

export interface FinancialHealthCell {
  readonly periodId: string;
  readonly periodLabel: string;
  readonly displayValue: string;
  readonly delta: number | null;
  readonly trend: FinancialHealthTrend;
  readonly trendLabel: string;
}

export interface FinancialHealthRow {
  readonly metricId: MetricId;
  readonly label: string;
  readonly direction: ImprovementDirection;
  readonly cells: readonly FinancialHealthCell[];
}

export interface FinancialHealthHeatmapModel {
  readonly periods: readonly { readonly periodId: string; readonly label: string }[];
  readonly rows: readonly FinancialHealthRow[];
}

const METRICS: readonly FinancialHealthMetricDefinition[] = [
  { metricId: 'revenue_yoy_growth', fallbackLabel: '매출 성장률', direction: 'higher' },
  { metricId: 'operating_margin', fallbackLabel: '영업이익률', direction: 'higher' },
  { metricId: 'net_margin', fallbackLabel: '순이익률', direction: 'higher' },
  { metricId: 'free_cash_flow_margin', fallbackLabel: 'FCF 마진', direction: 'higher' },
  { metricId: 'debt_ratio', fallbackLabel: '부채비율', direction: 'lower' },
  { metricId: 'net_debt_ratio', fallbackLabel: '순차입금비율', direction: 'lower' },
];

const TREND_LABELS: Readonly<Record<FinancialHealthTrend, string>> = {
  baseline: '기준',
  'strong-improvement': '큰 개선',
  improvement: '개선',
  stable: '유지',
  decline: '악화',
  'strong-decline': '큰 악화',
  na: 'NA',
};

function availableValue(observation: MetricObservation | undefined): number | null {
  if (!observation || observation.status !== 'available') return null;
  const value = Number(observation.normalizedValue);
  return Number.isFinite(value) ? value : null;
}

export function classifyFinancialHealthTrend(
  previous: number,
  current: number,
  direction: ImprovementDirection,
): FinancialHealthTrend {
  const rawDelta = current - previous;
  const improvement = direction === 'higher' ? rawDelta : -rawDelta;
  if (improvement >= 2) return 'strong-improvement';
  if (improvement >= 0.5) return 'improvement';
  if (improvement > -0.5) return 'stable';
  if (improvement > -2) return 'decline';
  return 'strong-decline';
}

export function buildFinancialHealthHeatmap(
  dashboard: BiDashboardSnapshot,
  range: PeriodRange,
  size: CardSize,
): FinancialHealthHeatmapModel {
  const selectedPeriods = selectPeriods(dashboard.periods, range);
  const visiblePeriods = size === 'M' ? selectedPeriods.slice(-6) : selectedPeriods;
  const rows = METRICS.map((definition): FinancialHealthRow => {
    const series = dashboard.metrics[definition.metricId];
    const observations = new Map(
      series?.observations.map((observation) => [observation.periodId, observation]),
    );
    let previousValue: number | null = null;
    const cells = visiblePeriods.map((period): FinancialHealthCell => {
      const observation = observations.get(period.periodId);
      const currentValue = availableValue(observation);
      if (currentValue === null || !series) {
        previousValue = null;
        return {
          periodId: period.periodId,
          periodLabel: period.label,
          displayValue: 'NA',
          delta: null,
          trend: 'na',
          trendLabel: TREND_LABELS.na,
        };
      }
      const delta = previousValue === null ? null : currentValue - previousValue;
      const trend = previousValue === null
        ? 'baseline'
        : classifyFinancialHealthTrend(previousValue, currentValue, definition.direction);
      previousValue = currentValue;
      return {
        periodId: period.periodId,
        periodLabel: period.label,
        displayValue: formatMetricValue(series, observation ?? null),
        delta,
        trend,
        trendLabel: TREND_LABELS[trend],
      };
    });
    return {
      metricId: definition.metricId,
      label: series?.label ?? definition.fallbackLabel,
      direction: definition.direction,
      cells,
    };
  });

  return {
    periods: visiblePeriods.map((period) => ({ periodId: period.periodId, label: period.label })),
    rows,
  };
}
