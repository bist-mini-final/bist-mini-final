import type {
  BiDashboardSnapshot,
  BiEvidence,
  CardSize,
  MetricId,
  MetricSeries,
  PeriodKind,
  PeriodRange,
  ValueKind,
} from '../types';
import { selectObservations, selectPeriods } from './periods';
import { formatAmountValue } from './formatMetric';

export interface BiChartPoint {
  readonly periodId: string;
  readonly periodLabel: string;
  readonly periodKind: PeriodKind;
  readonly values: Readonly<Partial<Record<MetricId, number | null>>>;
  readonly evidence: readonly BiEvidence[];
}

export interface BiChartSeriesMeta {
  readonly metricId: MetricId;
  readonly label: string;
}

interface ChartViewModelInput {
  readonly dashboard: BiDashboardSnapshot;
  readonly metricIds: readonly MetricId[];
  readonly range: PeriodRange;
  readonly size: CardSize;
}

const COMPACT_NUMBER = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 1 });

function readValue(series: MetricSeries | undefined, periodId: string): number | null {
  const observation = series?.observations.find((candidate) => candidate.periodId === periodId);
  if (!observation || observation.status !== 'available') return null;
  const value = Number(observation.normalizedValue);
  return Number.isFinite(value) ? value : null;
}

function readEvidence(series: MetricSeries | undefined, periodId: string): readonly BiEvidence[] {
  return series?.observations.find((candidate) => candidate.periodId === periodId)?.evidence ?? [];
}

export function buildChartPoints(input: ChartViewModelInput): readonly BiChartPoint[] {
  const { dashboard, metricIds, range, size } = input;
  const selectedPeriods = selectPeriods(dashboard.periods, range);
  const referenceSeries = dashboard.metrics[metricIds[0] ?? 'revenue'];
  const distinctPeriodIds = referenceSeries
    ? new Set(selectObservations(referenceSeries, selectedPeriods).map((observation) => observation.periodId))
    : new Set(selectedPeriods.map((period) => period.periodId));
  const periods = selectedPeriods.filter((period) => distinctPeriodIds.has(period.periodId));
  const visiblePeriods = size === 'S'
    ? periods.slice(-5)
    : size === 'M'
      ? periods.slice(-6)
      : periods;

  return visiblePeriods.map((period) => {
    const values: Partial<Record<MetricId, number | null>> = {};
    const evidence: BiEvidence[] = [];
    for (const metricId of metricIds) {
      const series = dashboard.metrics[metricId];
      values[metricId] = readValue(series, period.periodId);
      evidence.push(...readEvidence(series, period.periodId));
    }
    return {
      periodId: period.periodId,
      periodLabel: period.label,
      periodKind: period.kind,
      values,
      evidence,
    };
  });
}

/**
 * Builds chart series metadata for metrics available in the dashboard.
 *
 * @param metricIds - Identifiers of the metrics to include, in display order
 * @returns Metadata for each available metric
 */
export function getChartSeries(
  dashboard: BiDashboardSnapshot,
  metricIds: readonly MetricId[],
): readonly BiChartSeriesMeta[] {
  return metricIds.flatMap((metricId) => {
    const series = dashboard.metrics[metricId];
    return series ? [{ metricId, label: series.label }] : [];
  });
}

/**
 * Formats a chart value according to its value kind and unit.
 *
 * @param value - The value to format, or `null` when data is unavailable
 * @param valueKind - The kind of value being formatted
 * @param unit - Optional currency and scale information for amount values
 * @returns The formatted value, or `데이터 없음` when the value is `null`
 */
export function formatChartValue(
  value: number | null,
  valueKind: ValueKind,
  unit: Pick<MetricSeries, 'currency' | 'scale'> | null = null,
): string {
  if (value === null) return '데이터 없음';
  if (valueKind === 'percent') return `${COMPACT_NUMBER.format(value)}%`;
  return formatAmountValue(value, unit);
}

/**
 * Formats a chart axis value according to its metric kind and unit.
 *
 * @param value - The value to format
 * @param valueKind - The kind of metric represented by the value
 * @param unit - Optional currency and scale information for amount formatting
 * @returns The formatted axis value
 */
export function formatChartAxis(
  value: number,
  valueKind: ValueKind,
  unit: Pick<MetricSeries, 'currency' | 'scale'> | null = null,
): string {
  if (valueKind === 'percent') return `${COMPACT_NUMBER.format(value)}%`;
  return formatAmountValue(value, unit, true);
}
