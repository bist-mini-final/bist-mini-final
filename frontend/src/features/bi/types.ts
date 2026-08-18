export const METRIC_IDS = [
  'revenue',
  'revenue_yoy_growth',
  'operating_income',
  'operating_margin',
  'net_income',
  'net_margin',
  'operating_cash_flow',
  'capital_expenditure',
  'free_cash_flow',
  'cash_and_short_term_investments',
  'short_term_debt',
  'current_portion_of_long_term_debt',
  'long_term_debt',
  'total_debt',
  'net_debt',
  'total_assets',
  'total_liabilities',
  'total_equity',
] as const;

export type MetricId = (typeof METRIC_IDS)[number];
export type MetricStatus = 'available' | 'missing' | 'ambiguous' | 'invalid' | 'not_meaningful';
export type SnapshotStatus = 'ready' | 'partial';
export type RefreshStatus = 'idle' | 'queued' | 'profiling' | 'extracting' | 'materializing' | 'failed';
export type PeriodKind = 'fy' | 'ltm';
export type ValueKind = 'amount' | 'percent';
export type AmountScale = 'ones' | 'thousands' | 'millions' | 'billions';
export type PeriodRange = '최근 3개' | '최근 5개' | '전체';
export type CardSize = 'S' | 'M' | 'L';
export type CardState = 'ready' | 'partial' | 'missing' | 'ambiguous' | 'invalid';

export interface BiCompany {
  readonly companyId: string;
  readonly displayName: string;
}

export interface BiSnapshotMeta {
  readonly snapshotId: string;
  readonly workbookHash: string;
  readonly status: SnapshotStatus;
  readonly generatedAt: string;
  readonly catalogVersion: string;
  readonly formulaVersion: string;
}

export interface BiRefreshState {
  readonly status: RefreshStatus;
  readonly jobId: string | null;
  readonly startedAt: string | null;
  readonly message: string | null;
}

export interface BiPeriod {
  readonly periodId: string;
  readonly kind: PeriodKind;
  readonly label: string;
  readonly sourceLabel: string;
  readonly endDate: string | null;
  readonly ordinal: number;
}

export interface BiEvidence {
  readonly cellId: string;
  readonly sheetName: string;
  readonly cellCoord: string;
  readonly sourceText: string;
}

interface ObservationBase {
  readonly periodId: string;
  readonly rawValue: string | null;
  readonly evidence: readonly BiEvidence[];
  readonly notes: readonly string[];
}

export interface AvailableObservation extends ObservationBase {
  readonly status: 'available';
  readonly normalizedValue: string;
}

export interface UnavailableObservation extends ObservationBase {
  readonly status: Exclude<MetricStatus, 'available'>;
  readonly normalizedValue: null;
  readonly reason: string;
}

export type MetricObservation = AvailableObservation | UnavailableObservation;

export interface MetricSeries {
  readonly metricId: MetricId;
  readonly label: string;
  readonly valueKind: ValueKind;
  readonly currency: string | null;
  readonly scale: AmountScale | null;
  readonly status: MetricStatus;
  readonly observations: readonly MetricObservation[];
}

export interface BiIssue {
  readonly code: string;
  readonly message: string;
  readonly metricId: MetricId | null;
}

export interface BiDashboardSnapshot {
  readonly schemaVersion: 1;
  readonly company: BiCompany;
  readonly snapshot: BiSnapshotMeta;
  readonly refresh: BiRefreshState;
  readonly periods: readonly BiPeriod[];
  readonly metrics: Readonly<Partial<Record<MetricId, MetricSeries>>>;
  readonly issues: readonly BiIssue[];
}

export interface BiCardLayoutItem {
  readonly cardId: BiCardId;
  readonly size: CardSize;
}

export type BiCardId =
  | 'revenue_growth'
  | 'profitability'
  | 'cash_flow'
  | 'stability'
  | 'financial_scale';
