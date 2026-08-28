import type { LeagueCompany } from './leagueTypes';

export type RankingMetric =
  | 'composite'
  | 'revenue'
  | 'operatingIncome'
  | 'revenueCagr'
  | 'operatingMargin';

export type DisplayDirection = 'best-first' | 'worst-first';

export interface RankedCompany {
  readonly company: LeagueCompany;
  readonly rank: number;
  readonly metricValue: number;
}

export const RANKING_METRICS: Readonly<Record<RankingMetric, { readonly label: string; readonly shortLabel: string }>> = {
  composite: { label: '종합점수', shortLabel: '종합' },
  revenue: { label: '매출액', shortLabel: '매출' },
  operatingIncome: { label: '영업이익', shortLabel: '영업이익' },
  revenueCagr: { label: '5개년 매출 성장률', shortLabel: '성장률' },
  operatingMargin: { label: '영업이익률', shortLabel: '이익률' },
};

export function latestHistoricalCandle(company: LeagueCompany) {
  return [...company.candles]
    .filter((candle) => candle.periodType === 'historical')
    .sort((left, right) => right.year - left.year)[0];
}

export function metricValue(company: LeagueCompany, metric: RankingMetric): number {
  const latest = latestHistoricalCandle(company);
  switch (metric) {
    case 'composite':
      return company.compositeScore;
    case 'revenue':
      return latest?.revenue ?? Number.NEGATIVE_INFINITY;
    case 'operatingIncome':
      return latest?.operatingIncome ?? Number.NEGATIVE_INFINITY;
    case 'revenueCagr':
      return company.revenueCagr;
    case 'operatingMargin':
      return company.operatingMargin;
  }
}

function compareMetric(left: LeagueCompany, right: LeagueCompany, metric: RankingMetric): number {
  return metricValue(right, metric) - metricValue(left, metric);
}

/** Competition ranking for the selected metric: equal values share a rank (1, 2, 2, 4). */
export function rankCompaniesByMetric(
  companies: readonly LeagueCompany[],
  metric: RankingMetric,
): readonly RankedCompany[] {
  const meritOrder = [...companies].sort((left, right) => compareMetric(left, right, metric));
  return meritOrder.map((company, index) => ({
    company,
    rank: index > 0 && metricValue(company, metric) === metricValue(meritOrder[index - 1], metric)
      ? (index > 1 ? metricRankAt(meritOrder, index - 1, metric) : 1)
      : index + 1,
    metricValue: metricValue(company, metric),
  }));
}

/** Official composite-score ranking used by the fixed TOP 3 summary. */
export function rankCompaniesByComposite(
  companies: readonly LeagueCompany[],
): readonly RankedCompany[] {
  return rankCompaniesByMetric(companies, 'composite');
}

function metricRankAt(
  companies: readonly LeagueCompany[],
  index: number,
  metric: RankingMetric,
): number {
  let firstEqual = index;
  while (
    firstEqual > 0
    && metricValue(companies[firstEqual], metric) === metricValue(companies[firstEqual - 1], metric)
  ) {
    firstEqual -= 1;
  }
  return firstEqual + 1;
}

export function orderForDisplay(
  ranked: readonly RankedCompany[],
  metric: RankingMetric,
  direction: DisplayDirection,
): readonly RankedCompany[] {
  const multiplier = direction === 'best-first' ? 1 : -1;
  return [...ranked].sort((left, right) => {
    const metricDifference = compareMetric(left.company, right.company, metric) * multiplier;
    if (metricDifference !== 0) return metricDifference;
    return left.rank - right.rank;
  });
}

export function toggleCompanySelection(
  selected: ReadonlySet<string>,
  companyId: string,
  maximum = 2,
): ReadonlySet<string> {
  const next = new Set(selected);
  if (next.has(companyId)) {
    next.delete(companyId);
    return next;
  }
  if (next.size >= maximum) next.delete(next.values().next().value as string);
  next.add(companyId);
  return next;
}
