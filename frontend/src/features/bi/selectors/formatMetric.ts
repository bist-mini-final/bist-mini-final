import type { MetricObservation, MetricSeries } from '../types';

const AMOUNT_FORMATTER = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 1 });
const PERCENT_FORMATTER = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 1, signDisplay: 'exceptZero' });

export function formatMetricValue(series: MetricSeries, observation: MetricObservation | null): string {
  if (!observation) return '데이터 없음';
  if (observation.status === 'ambiguous') {
    return observation.rawValue
      ? `${observation.rawValue} (단위 확인 필요)`
      : '확인 필요';
  }
  if (observation.status === 'invalid') return '검증 실패';
  if (observation.status === 'not_meaningful') return '의미 없음';
  if (observation.status === 'missing') return '데이터 없음';
  const value = Number(observation.normalizedValue);
  if (!Number.isFinite(value)) return '확인 필요';
  if (series.valueKind === 'percent') return `${PERCENT_FORMATTER.format(value)}%`;

  const absolute = Math.abs(value);
  if (absolute >= 1_000_000) return `${AMOUNT_FORMATTER.format(value / 1_000_000)}조원`;
  if (absolute >= 100) return `${AMOUNT_FORMATTER.format(value / 100)}억원`;
  return `${AMOUNT_FORMATTER.format(value)}백만원`;
}
