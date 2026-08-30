import type { ComparisonCompany, ComparisonPeriod } from './types';

export const SCORE_DIMENSIONS = [
  { key: 'growthScore', label: '성장성', weight: 0.35 },
  { key: 'profitabilityScore', label: '수익성', weight: 0.35 },
  { key: 'stabilityScore', label: '안정성', weight: 0.30 },
] as const;

export type ScoreDimension = (typeof SCORE_DIMENSIONS)[number];

export function formatAmount(value: number, company: ComparisonCompany): string {
  const currency = company.currency === 'USD'
    ? '$'
    : company.currency === 'KRW'
      ? '₩'
      : `${company.currency} `;
  const suffix = company.scale === 'millions'
    ? 'M'
    : company.scale === 'billions'
      ? 'B'
      : company.scale === 'thousands'
        ? 'K'
        : '';
  const sign = value < 0 ? '-' : '';
  return `${sign}${currency}${Math.round(Math.abs(value)).toLocaleString()}${suffix}`;
}

export function historicalPeriods(company: ComparisonCompany) {
  return [...company.periods]
    .filter((period) => period.periodType === 'historical')
    .sort((left, right) => left.year - right.year);
}

export function forecastPeriods(company: ComparisonCompany) {
  return [...company.periods]
    .filter((period) => period.periodType === 'forecast')
    .sort((left, right) => left.year - right.year);
}

export function scoreRank(
  companies: readonly ComparisonCompany[],
  company: ComparisonCompany,
  dimension: ScoreDimension,
): number {
  return companies.filter((candidate) => candidate[dimension.key] > company[dimension.key]).length + 1;
}

export function rankReason(
  company: ComparisonCompany,
  companies: readonly ComparisonCompany[],
): readonly string[] {
  const dimensions = SCORE_DIMENSIONS.map((dimension) => ({
    ...dimension,
    score: company[dimension.key],
    rank: scoreRank(companies, company, dimension),
    contribution: company[dimension.key] * dimension.weight,
  })).sort((left, right) => right.contribution - left.contribution);
  const strongest = dimensions[0];
  const weakest = [...dimensions].sort((left, right) => left.score - right.score)[0];
  const spread = strongest.score - weakest.score;

  const first = `${strongest.label} ${strongest.score.toFixed(1)}점(기업군 ${strongest.rank}위)이 가중 점수 ${strongest.contribution.toFixed(1)}점으로 가장 크게 기여했습니다.`;
  const second = spread < 8
    ? '세 평가축의 점수 차이가 작아 특정 지표에 치우치지 않은 균형형 평가입니다.'
    : `${weakest.label} ${weakest.score.toFixed(1)}점은 세 평가축 중 가장 낮아 종합순위의 주요 감점 요인입니다.`;
  return [first, second];
}

export function signedPoint(value: number): string {
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}%p`;
}

export function percentChange(values: readonly number[]): number | null {
  if (values.length < 2 || values[0] === 0) return null;
  return ((values[values.length - 1] - values[0]) / Math.abs(values[0])) * 100;
}

export interface TrendPoint {
  readonly year: number;
  readonly value: number;
}

export function indexedSeries(periods: readonly ComparisonPeriod[]): readonly TrendPoint[] {
  if (!periods.length) return [];
  const first = periods[0].revenue;
  return periods.map((period) => ({
    year: period.year,
    value: first === 0 ? 100 : (period.revenue / first) * 100,
  }));
}
