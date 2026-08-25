import type { MetricObservation, MetricSeries } from '../types';

const AMOUNT_FORMATTER = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 1 });
const PERCENT_FORMATTER = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 1, signDisplay: 'exceptZero' });
const SCALE_MULTIPLIER = {
  ones: 1,
  thousands: 1_000,
  millions: 1_000_000,
  billions: 1_000_000_000,
} as const;
const SCALE_SUFFIX = {
  ones: '',
  thousands: 'K',
  millions: 'M',
  billions: 'B',
} as const;
const CURRENCY_SYMBOL: Readonly<Record<string, string>> = {
  USD: '$',
  EUR: '€',
  GBP: '£',
  JPY: '¥',
};

function formatKrwAmount(baseValue: number, axis: boolean): string {
  const absolute = Math.abs(baseValue);
  if (absolute >= 1_000_000_000_000) {
    return `${AMOUNT_FORMATTER.format(baseValue / 1_000_000_000_000)}조${axis ? '' : '원'}`;
  }
  if (absolute >= 100_000_000) {
    return `${AMOUNT_FORMATTER.format(baseValue / 100_000_000)}억${axis ? '' : '원'}`;
  }
  if (absolute >= 1_000_000) {
    return `${AMOUNT_FORMATTER.format(baseValue / 1_000_000)}백만${axis ? '' : '원'}`;
  }
  if (absolute >= 1_000) {
    return `${AMOUNT_FORMATTER.format(baseValue / 1_000)}천${axis ? '' : '원'}`;
  }
  return `${AMOUNT_FORMATTER.format(baseValue)}${axis ? '' : '원'}`;
}

function formatInternationalAmount(
  value: number,
  currency: string,
  scale: NonNullable<MetricSeries['scale']>,
): string {
  const symbol = CURRENCY_SYMBOL[currency];
  const formatted = `${AMOUNT_FORMATTER.format(Math.abs(value))}${SCALE_SUFFIX[scale]}`;
  const sign = value < 0 ? '-' : '';
  if (symbol) return `${sign}${symbol}${formatted}`;
  return `${sign}${currency} ${formatted}`;
}

export function formatAmountValue(
  value: number,
  unit: Pick<MetricSeries, 'currency' | 'scale'> | null,
  axis = false,
): string {
  if (!unit?.scale) {
    return `${AMOUNT_FORMATTER.format(value)}${axis ? '?' : ' (배율 확인 필요)'}`;
  }
  if (!unit.currency) {
    return `${AMOUNT_FORMATTER.format(value)} ${unit.scale}${axis ? '?' : ' (통화 확인 필요)'}`;
  }
  if (unit.currency === 'KRW') {
    return formatKrwAmount(value * SCALE_MULTIPLIER[unit.scale], axis);
  }
  return formatInternationalAmount(value, unit.currency, unit.scale);
}

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

  return formatAmountValue(value, series);
}
