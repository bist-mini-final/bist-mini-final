import type {
  BiDashboardSnapshot,
  BiPeriod,
  MetricId,
  MetricSeries,
  MetricStatus,
  ValueKind,
} from '../types';

interface MetricSeed {
  readonly metricId: MetricId;
  readonly label: string;
  readonly valueKind: ValueKind;
  readonly values: readonly number[];
}

interface FixtureConfig {
  readonly companyId: string;
  readonly displayName: string;
  readonly snapshotId: string;
  readonly periodCount: number;
  readonly includeLtm: boolean;
  readonly refreshStatus?: 'extracting' | 'failed';
  readonly refreshMessage?: string;
  readonly statusOverrides?: Readonly<Partial<Record<MetricId, Exclude<MetricStatus, 'available'>>>>;
}

const PERIODS = [
  { periodId: 'fy-2021', kind: 'fy', label: 'FY2021', sourceLabel: 'FY-4', endDate: '2021-12-31', ordinal: 1 },
  { periodId: 'fy-2022', kind: 'fy', label: 'FY2022', sourceLabel: 'FY-3', endDate: '2022-12-31', ordinal: 2 },
  { periodId: 'fy-2023', kind: 'fy', label: 'FY2023', sourceLabel: 'FY-2', endDate: '2023-12-31', ordinal: 3 },
  { periodId: 'fy-2024', kind: 'fy', label: 'FY2024', sourceLabel: 'FY-1', endDate: '2024-12-31', ordinal: 4 },
  { periodId: 'fy-2025', kind: 'fy', label: 'FY2025', sourceLabel: 'FY0', endDate: '2025-12-31', ordinal: 5 },
  { periodId: 'ltm-2026-q2', kind: 'ltm', label: 'LTM 2026 Q2', sourceLabel: 'LTM', endDate: '2026-06-30', ordinal: 6 },
] as const satisfies readonly BiPeriod[];

const METRIC_SEEDS = [
  { metricId: 'revenue', label: '매출', valueKind: 'amount', values: [810000, 930000, 1040000, 1180000, 1280000, 1365000] },
  { metricId: 'revenue_yoy_growth', label: '매출 성장률', valueKind: 'percent', values: [6.2, 14.8, 11.8, 13.5, 8.5, 7.2] },
  { metricId: 'operating_income', label: '영업이익', valueKind: 'amount', values: [92000, 108000, 126000, 149000, 164000, 178000] },
  { metricId: 'operating_margin', label: '영업이익률', valueKind: 'percent', values: [11.4, 11.6, 12.1, 12.6, 12.8, 13.0] },
  { metricId: 'net_income', label: '순이익', valueKind: 'amount', values: [71000, 83000, 97000, 112000, 121000, 129000] },
  { metricId: 'net_margin', label: '순이익률', valueKind: 'percent', values: [8.8, 8.9, 9.3, 9.5, 9.5, 9.5] },
  { metricId: 'operating_cash_flow', label: '영업현금흐름', valueKind: 'amount', values: [104000, 119000, 132000, 151000, 159000, 171000] },
  { metricId: 'capital_expenditure', label: '자본적 지출', valueKind: 'amount', values: [-39000, -42000, -44000, -47000, -48000, -51000] },
  { metricId: 'free_cash_flow', label: '잉여현금흐름', valueKind: 'amount', values: [65000, 77000, 88000, 104000, 111000, 120000] },
  { metricId: 'cash_and_short_term_investments', label: '현금 및 단기금융상품', valueKind: 'amount', values: [268000, 284000, 301000, 326000, 349000, 361000] },
  { metricId: 'short_term_debt', label: '단기차입금', valueKind: 'amount', values: [81000, 86000, 91000, 94000, 97000, 98000] },
  { metricId: 'current_portion_of_long_term_debt', label: '유동성 장기부채', valueKind: 'amount', values: [23000, 24000, 26000, 27000, 29000, 30000] },
  { metricId: 'long_term_debt', label: '장기차입금', valueKind: 'amount', values: [372000, 389000, 405000, 423000, 431000, 441000] },
  { metricId: 'total_debt', label: '총차입금', valueKind: 'amount', values: [476000, 499000, 522000, 544000, 557000, 569000] },
  { metricId: 'net_debt', label: '순차입금', valueKind: 'amount', values: [208000, 215000, 221000, 218000, 208000, 208000] },
  { metricId: 'total_assets', label: '총자산', valueKind: 'amount', values: [2980000, 3190000, 3420000, 3710000, 3940000, 4120000] },
  { metricId: 'total_liabilities', label: '총부채', valueKind: 'amount', values: [1680000, 1780000, 1880000, 2010000, 2110000, 2190000] },
  { metricId: 'total_equity', label: '총자본', valueKind: 'amount', values: [1300000, 1410000, 1540000, 1700000, 1830000, 1930000] },
] as const satisfies readonly MetricSeed[];

function createPeriods(config: FixtureConfig): readonly BiPeriod[] {
  const fyPeriods = PERIODS.filter((period) => period.kind === 'fy').slice(-config.periodCount);
  return config.includeLtm ? [...fyPeriods, PERIODS[PERIODS.length - 1]] : fyPeriods;
}

function createSeries(
  seed: MetricSeed,
  periods: readonly BiPeriod[],
  status: MetricStatus = 'available',
): MetricSeries {
  return {
    metricId: seed.metricId,
    label: seed.label,
    valueKind: seed.valueKind,
    currency: seed.valueKind === 'amount' ? 'KRW' : null,
    scale: seed.valueKind === 'amount' ? 'millions' : null,
    status,
    observations: periods.map((period, index) => {
      const sourceIndex = PERIODS.findIndex((candidate) => candidate.periodId === period.periodId);
      const value = seed.values[sourceIndex] ?? seed.values[seed.values.length - 1] ?? 0;
      const evidence = [{
        cellId: `${seed.metricId}:${period.periodId}`,
        sheetName: '재무요약',
        cellCoord: `${String.fromCharCode(66 + index)}${12 + METRIC_SEEDS.findIndex((candidate) => candidate.metricId === seed.metricId)}`,
        sourceText: `${seed.label} ${value}`,
      }];
      return status === 'available'
        ? { periodId: period.periodId, status: 'available', normalizedValue: String(value), rawValue: String(value), evidence, notes: [] }
        : {
            periodId: period.periodId,
            status,
            normalizedValue: null,
            rawValue: null,
            evidence,
            notes: [],
            reason: status === 'missing' ? '원본 셀에서 값을 찾지 못했습니다.' : '원본 값 확인이 필요합니다.',
          };
    }),
  };
}

function createDashboardFixture(config: FixtureConfig): BiDashboardSnapshot {
  const periods = createPeriods(config);
  const metrics: Partial<Record<MetricId, MetricSeries>> = {};
  for (const seed of METRIC_SEEDS) {
    const status = config.statusOverrides?.[seed.metricId] ?? 'available';
    metrics[seed.metricId] = createSeries(seed, periods, status);
  }
  const issues = METRIC_SEEDS.flatMap((seed) => {
    const status = config.statusOverrides?.[seed.metricId];
    return status ? [{
      code: `fixture.${status}`,
      message: `${seed.metricId} 지표는 fixture에서 ${status} 상태입니다.`,
      metricId: seed.metricId,
    }] : [];
  });

  return {
    schemaVersion: 1,
    company: { companyId: config.companyId, displayName: config.displayName },
    snapshot: {
      snapshotId: config.snapshotId,
      workbookHash: `fixture-${config.companyId}`,
      status: issues.length > 0 ? 'partial' : 'ready',
      generatedAt: '2026-08-18T09:30:00+09:00',
      catalogVersion: 'fixture-v1',
      formulaVersion: 'fixture-v1',
    },
    refresh: {
      status: config.refreshStatus ?? 'idle',
      jobId: config.refreshStatus ? `fixture-job-${config.companyId}` : null,
      startedAt: config.refreshStatus ? '2026-08-18T10:00:00+09:00' : null,
      message: config.refreshMessage ?? null,
    },
    periods,
    metrics,
    issues,
  };
}

export const DASHBOARD_FIXTURES = [
  createDashboardFixture({
    companyId: 'bist-demo',
    displayName: 'BIST 데모 주식회사',
    snapshotId: 'fixture-ready-001',
    periodCount: 5,
    includeLtm: true,
  }),
  createDashboardFixture({
    companyId: 'green-labs',
    displayName: '그린랩스',
    snapshotId: 'fixture-partial-002',
    periodCount: 2,
    includeLtm: false,
    refreshStatus: 'extracting',
    refreshMessage: '새 파일에서 지표를 추출하고 있습니다. 이전 부분 완료 스냅샷을 표시합니다.',
    statusOverrides: { capital_expenditure: 'missing', free_cash_flow: 'missing', net_debt: 'ambiguous' },
  }),
  createDashboardFixture({
    companyId: 'long-name',
    displayName: '아주 긴 기업명을 가진 레이아웃 검증 기업',
    snapshotId: 'fixture-stress-003',
    periodCount: 5,
    includeLtm: true,
    refreshStatus: 'failed',
    refreshMessage: '새 파일 처리에 실패해 검증된 이전 스냅샷을 유지합니다.',
    statusOverrides: { total_equity: 'invalid' },
  }),
] as const satisfies readonly BiDashboardSnapshot[];
