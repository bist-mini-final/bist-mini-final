import type {
  BiDashboardSnapshot,
  BiEvidence,
  BiPeriod,
  MetricId,
  MetricObservation,
} from '../bi/types';

export const COMPARISON_COMPANIES = [
  { key: 'bistelligence', label: 'Bistelligence', color: '#107c41', matches: /bistelligence/i },
  { key: 'coldplay', label: 'Coldplay', color: '#16a34a', matches: /coldplay/i },
  { key: 'dh-innovation', label: 'DH Innovation', color: '#064e3b', matches: /dh\s*innovation/i },
] as const;

export type ComparisonCompanyKey = (typeof COMPARISON_COMPANIES)[number]['key'];

export interface ComparisonDashboard {
  readonly key: ComparisonCompanyKey;
  readonly label: string;
  readonly color: string;
  readonly dashboard: BiDashboardSnapshot;
}

export interface ComparisonPoint {
  readonly year: number;
  readonly revenue: number;
  readonly operatingIncome: number;
}

export interface CompanyComparisonResult {
  readonly key: ComparisonCompanyKey;
  readonly label: string;
  readonly color: string;
  readonly currency: string;
  readonly scale: string;
  readonly points: readonly ComparisonPoint[];
  readonly revenueCagr: number;
  readonly operatingMargin: number;
  readonly liabilitiesToAssets: number;
  readonly netDebt: number;
}

export interface ComparisonInsight {
  readonly type: 'growth' | 'profitability' | 'risk';
  readonly title: string;
  readonly body: string;
  readonly evidenceIds: readonly number[];
}

export interface ComparisonEvidenceRow {
  readonly id: number;
  readonly metric: string;
  readonly basis: string;
  readonly sources: readonly string[];
  readonly evidence: readonly BiEvidence[];
  readonly verified: boolean;
}

export interface ComparisonViewModel {
  readonly startYear: number;
  readonly endYear: number;
  readonly companies: readonly CompanyComparisonResult[];
  readonly insights: readonly ComparisonInsight[];
  readonly evidenceRows: readonly ComparisonEvidenceRow[];
}

export interface NetDebtPresentation {
  readonly label: '순현금' | '순부채';
  readonly value: number;
  readonly description: string;
}

interface ValueWithEvidence {
  readonly value: number;
  readonly evidence: readonly BiEvidence[];
}

function periodYear(period: BiPeriod): number | null {
  if (period.kind !== 'fy') return null;
  const value = period.endDate?.slice(0, 4) ?? period.label.match(/\d{4}/)?.[0];
  const year = Number(value);
  return Number.isInteger(year) ? year : null;
}

function periodForYear(dashboard: BiDashboardSnapshot, year: number): BiPeriod | undefined {
  return dashboard.periods.find((period) => periodYear(period) === year);
}

function observationForYear(
  dashboard: BiDashboardSnapshot,
  metricId: MetricId,
  year: number,
): MetricObservation | undefined {
  const period = periodForYear(dashboard, year);
  if (!period) return undefined;
  return dashboard.metrics[metricId]?.observations.find(
    (observation) => observation.periodId === period.periodId,
  );
}

function availableValue(
  dashboard: BiDashboardSnapshot,
  metricId: MetricId,
  year: number,
): ValueWithEvidence | null {
  const observation = observationForYear(dashboard, metricId, year);
  if (!observation || observation.status !== 'available') return null;
  const value = Number(observation.normalizedValue);
  return Number.isFinite(value) ? { value, evidence: observation.evidence } : null;
}

function requireValue(
  company: ComparisonDashboard,
  metricId: MetricId,
  year: number,
): ValueWithEvidence {
  const value = availableValue(company.dashboard, metricId, year);
  if (!value) {
    throw new Error(`${company.label}의 ${year}년 ${metricId} 지표가 없어 비교할 수 없습니다.`);
  }
  return value;
}

function dedupeEvidence(evidence: readonly BiEvidence[]): readonly BiEvidence[] {
  return [...new Map(evidence.map((item) => [item.cellId, item])).values()];
}

function formatPercent(value: number): string {
  return `${value.toFixed(1)}%`;
}

function formatAmount(value: number, currency: string, scale: string): string {
  const unit = scale === 'millions' ? '백만' : scale === 'billions' ? '십억' : '';
  return `${value.toLocaleString('ko-KR', { maximumFractionDigits: 1 })} ${currency} ${unit}`.trim();
}

export function presentNetDebt(netDebt: number): NetDebtPresentation {
  if (netDebt < 0) {
    return {
      label: '순현금',
      value: Math.abs(netDebt),
      description: '현금성 자산이 총차입금보다 많습니다.',
    };
  }
  if (netDebt === 0) {
    return {
      label: '순부채',
      value: 0,
      description: '현금성 자산과 총차입금 규모가 유사합니다.',
    };
  }
  return {
    label: '순부채',
    value: netDebt,
    description: '현금 차감 후에도 상환할 순차입금이 남아 있습니다.',
  };
}

export function getCommonFiscalYears(companies: readonly ComparisonDashboard[]): readonly number[] {
  if (companies.length === 0) return [];
  const yearSets = companies.map(({ dashboard }) => new Set(
    dashboard.periods.map(periodYear).filter((year): year is number => year !== null),
  ));
  return [...yearSets[0]].filter((year) => yearSets.every((set) => set.has(year))).sort((a, b) => a - b);
}

export function buildComparisonViewModel(
  companies: readonly ComparisonDashboard[],
  startYear: number,
  endYear: number,
): ComparisonViewModel {
  if (companies.length < 2 || companies.length > COMPARISON_COMPANIES.length) {
    throw new Error('기업 비교에는 2개 이상 3개 이하의 기업이 필요합니다.');
  }
  if (startYear >= endYear) throw new Error('비교 기간은 최소 2개 연도여야 합니다.');

  const commonYears = getCommonFiscalYears(companies);
  if (!commonYears.includes(startYear) || !commonYears.includes(endYear)) {
    throw new Error('세 기업에 공통으로 존재하는 회계연도를 선택해 주세요.');
  }
  const selectedYears = commonYears.filter((year) => year >= startYear && year <= endYear);

  const baseResults = companies.map((company) => {
    const startRevenue = requireValue(company, 'revenue', startYear);
    const endRevenue = requireValue(company, 'revenue', endYear);
    const operatingMargin = requireValue(company, 'operating_margin', endYear);
    const totalLiabilities = requireValue(company, 'total_liabilities', endYear);
    const totalAssets = requireValue(company, 'total_assets', endYear);
    const netDebt = requireValue(company, 'net_debt', endYear);
    if (startRevenue.value <= 0 || endRevenue.value < 0 || totalAssets.value <= 0) {
      throw new Error(`${company.label}의 계산 기준값이 유효하지 않습니다.`);
    }
    const yearGap = endYear - startYear;
    const revenueCagr = (Math.pow(endRevenue.value / startRevenue.value, 1 / yearGap) - 1) * 100;
    const liabilitiesToAssets = (totalLiabilities.value / totalAssets.value) * 100;
    const points = selectedYears.map((year) => ({
      year,
      revenue: requireValue(company, 'revenue', year).value,
      operatingIncome: requireValue(company, 'operating_income', year).value,
    }));
    const revenueSeries = company.dashboard.metrics.revenue;
    return {
      key: company.key,
      label: company.label,
      color: company.color,
      currency: revenueSeries?.currency ?? '',
      scale: revenueSeries?.scale ?? '',
      points,
      revenueCagr,
      operatingMargin: operatingMargin.value,
      liabilitiesToAssets,
      netDebt: netDebt.value,
    };
  });

  const results: readonly CompanyComparisonResult[] = baseResults;
  const growthLeader = [...results].sort((a, b) => b.revenueCagr - a.revenueCagr)[0];
  const profitLeader = [...results].sort((a, b) => b.operatingMargin - a.operatingMargin)[0];
  const riskCompany = [...results].sort((a, b) => b.liabilitiesToAssets - a.liabilitiesToAssets)[0];

  const evidenceRows: readonly ComparisonEvidenceRow[] = [
    {
      id: 1,
      metric: '매출 CAGR',
      basis: `${startYear}–${endYear} 연간`,
      sources: companies.map((company) => company.dashboard.source.fileName),
      evidence: dedupeEvidence(companies.flatMap((company) => [
        ...requireValue(company, 'revenue', startYear).evidence,
        ...requireValue(company, 'revenue', endYear).evidence,
      ])),
      verified: true,
    },
    {
      id: 2,
      metric: '영업이익률',
      basis: `${endYear}년`,
      sources: companies.map((company) => company.dashboard.source.fileName),
      evidence: dedupeEvidence(companies.flatMap((company) => requireValue(company, 'operating_margin', endYear).evidence)),
      verified: true,
    },
    {
      id: 3,
      metric: '총부채 / 총자산',
      basis: `${endYear}년`,
      sources: companies.map((company) => company.dashboard.source.fileName),
      evidence: dedupeEvidence(companies.flatMap((company) => [
        ...requireValue(company, 'total_liabilities', endYear).evidence,
        ...requireValue(company, 'total_assets', endYear).evidence,
      ])),
      verified: true,
    },
    {
      id: 4,
      metric: '순부채',
      basis: `${endYear}년`,
      sources: companies.map((company) => company.dashboard.source.fileName),
      evidence: dedupeEvidence(companies.flatMap((company) => requireValue(company, 'net_debt', endYear).evidence)),
      verified: true,
    },
  ];

  return {
    startYear,
    endYear,
    companies: results,
    evidenceRows,
    insights: [
      {
        type: 'growth',
        title: '성장',
        body: `${growthLeader.label}가 ${startYear}–${endYear} 매출 CAGR ${formatPercent(growthLeader.revenueCagr)}로 가장 높은 성장률을 기록했습니다. ${results.length}개 비교 기업의 시작·종료연도 매출 원본값을 같은 기간으로 환산해 비교했으며, ${results.map((company) => `${company.label} ${formatPercent(company.revenueCagr)}`).join(', ')} 순입니다. 기간을 변경하면 해당 구간의 시작·종료 매출로 CAGR을 다시 계산합니다.`,
        evidenceIds: [1],
      },
      {
        type: 'profitability',
        title: '수익성',
        body: `${profitLeader.label}의 ${endYear}년 영업이익률은 ${formatPercent(profitLeader.operatingMargin)}로 ${results.length}개 비교 기업 중 가장 높습니다. 동일 종료연도의 영업이익을 매출로 나눈 비율을 비교했으며, ${results.map((company) => `${company.label} ${formatPercent(company.operatingMargin)}`).join(', ')}입니다. 따라서 매출 규모와 별개로 본업의 수익 창출 효율은 ${profitLeader.label}가 가장 우수합니다.`,
        evidenceIds: [2],
      },
      {
        type: 'risk',
        title: '리스크',
        body: `${riskCompany.label}의 ${endYear}년 총부채/총자산 비율은 ${formatPercent(riskCompany.liabilitiesToAssets)}로 ${results.length}개 비교 기업 중 가장 높고, 순부채는 ${formatAmount(riskCompany.netDebt, riskCompany.currency, riskCompany.scale)}입니다. 이 비율은 기업 자산 중 부채로 조달된 비중을 뜻하며 값이 높을수록 재무 부담이 큽니다. 순부채가 음수인 기업은 보유 현금성 자산이 총차입금보다 많다는 의미이므로 두 지표를 함께 해석해야 합니다.`,
        evidenceIds: [3, 4],
      },
    ],
  };
}
