import type { BiCardDefinition } from '../config/cardRegistry';
import type {
  BiDashboardSnapshot,
  BiEvidence,
  CardSize,
  CardState,
  MetricId,
  MetricSeries,
  MetricStatus,
  PeriodRange,
} from '../types';
import { formatMetricValue } from './formatMetric';
import { selectObservations, selectPeriods, selectRepresentativeObservation } from './periods';

interface BiValueRow {
  readonly periodLabel: string;
  readonly value: string;
  readonly status: MetricStatus;
}

export interface BiCardViewModel {
  readonly state: CardState;
  readonly stateLabel: string;
  readonly primaryLabel: string;
  readonly primaryValue: string;
  readonly secondaryLabel: string | null;
  readonly secondaryValue: string | null;
  readonly unitLabel: string;
  readonly rows: readonly BiValueRow[];
  readonly evidence: readonly BiEvidence[];
}

interface CardViewModelInput {
  readonly definition: BiCardDefinition;
  readonly dashboard: BiDashboardSnapshot;
  readonly range: PeriodRange;
  readonly size: CardSize;
}

const STATE_LABELS: Readonly<Record<CardState, string>> = {
  ready: '사용 가능',
  partial: '일부 데이터',
  missing: '데이터 없음',
  ambiguous: '확인 필요',
  invalid: '검증 실패',
};

function getCardState(definition: BiCardDefinition, metrics: BiDashboardSnapshot['metrics']): CardState {
  const primaryStatus = metrics[definition.primaryMetric]?.status ?? 'missing';
  const statuses = definition.requiredMetrics.map((metricId) => metrics[metricId]?.status ?? 'missing');
  const availableCount = statuses.filter((status) => status === 'available').length;

  if (definition.id === 'financial_health_heatmap' && availableCount > 0) {
    return availableCount === statuses.length ? 'ready' : 'partial';
  }

  // If the primary metric has available data, allow the chart to render (ready or partial)
  if (primaryStatus === 'available') {
    const allAvailable = statuses.every((status) => status === 'available');
    return allAvailable ? 'ready' : 'partial';
  }

  if (statuses.includes('invalid')) return 'invalid';
  if (statuses.includes('ambiguous')) return 'ambiguous';
  if (availableCount === 0) return 'missing';
  if (availableCount < statuses.length) return 'partial';
  return 'ready';
}

function getSeries(metrics: BiDashboardSnapshot['metrics'], metricId: MetricId): MetricSeries | null {
  return metrics[metricId] ?? null;
}

/**
 * Formats the display label for a metric series unit.
 *
 * @param series - The metric series whose unit should be labeled
 * @returns The localized unit label, or a message indicating that the unit is unavailable or requires confirmation
 */
function getUnitLabel(series: MetricSeries | null): string {
  if (!series) return '단위 없음';
  if (series.valueKind === 'percent') return '%';
  if (!series.currency || !series.scale) return '단위 확인 필요';
  if (series.currency === 'KRW' && series.scale === 'millions') return '원본 단위: 백만원';
  return `원본 단위: ${series.currency} ${series.scale}`;
}

/**
 * Builds the rendered view model for a BI card.
 *
 * @param input - The card definition, dashboard metrics, period range, and card size
 * @returns The card state, formatted metric values, period rows, unit label, and evidence
 */
export function buildCardViewModel(input: CardViewModelInput): BiCardViewModel {
  const { definition, dashboard, range, size } = input;
  const selectedPeriods = selectPeriods(dashboard.periods, range);
  const visiblePeriods = size === 'M' ? selectedPeriods.slice(-6) : selectedPeriods;
  const primarySeries = getSeries(dashboard.metrics, definition.primaryMetric);
  const secondarySeries = definition.secondaryMetric
    ? getSeries(dashboard.metrics, definition.secondaryMetric)
    : null;
  const primaryObservation = primarySeries
    ? selectRepresentativeObservation(primarySeries, selectedPeriods)
    : null;
  const secondaryObservation = secondarySeries
    ? selectRepresentativeObservation(secondarySeries, selectedPeriods)
    : null;
  const rows = size === 'S' || !primarySeries
    ? []
    : selectObservations(primarySeries, visiblePeriods).map((observation) => {
        const period = dashboard.periods.find((candidate) => candidate.periodId === observation.periodId);
        return {
          periodLabel: period?.label ?? observation.periodId,
          value: formatMetricValue(primarySeries, observation),
          status: observation.status,
        };
      });

  return {
    state: getCardState(definition, dashboard.metrics),
    stateLabel: STATE_LABELS[getCardState(definition, dashboard.metrics)],
    primaryLabel: primarySeries?.label ?? definition.title,
    primaryValue: primarySeries ? formatMetricValue(primarySeries, primaryObservation) : '데이터 없음',
    secondaryLabel: secondarySeries?.label ?? null,
    secondaryValue: secondarySeries ? formatMetricValue(secondarySeries, secondaryObservation) : null,
    unitLabel: getUnitLabel(primarySeries),
    rows,
    evidence: primaryObservation?.evidence ?? [],
  };
}
