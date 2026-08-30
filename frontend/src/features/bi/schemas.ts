import { z } from 'zod';
import {
  METRIC_IDS,
  type BiCompanyListResponse,
  type BiDashboardSnapshot,
  type BiEvidence,
  type BiMaterializationJob,
  type BiMaterializationAccepted,
  type BiMaterializationCandidateListResponse,
  type BiQuestionJobProgress,
  type MetricObservation,
  type MetricSeries,
} from './types';

const MetricIdSchema = z.enum(METRIC_IDS);
const MetricStatusSchema = z.enum(['available', 'missing', 'ambiguous', 'invalid', 'not_meaningful']);
const UnavailableStatusSchema = z.enum(['missing', 'ambiguous', 'invalid', 'not_meaningful']);
const SnapshotStatusSchema = z.enum(['ready', 'partial']);
const RefreshStatusSchema = z.enum(['idle', 'queued', 'indexing', 'profiling', 'extracting', 'materializing', 'failed']);
const MaterializationStatusSchema = z.enum(['queued', 'indexing', 'profiling', 'extracting', 'materializing', 'ready', 'partial', 'failed']);
const PeriodKindSchema = z.enum(['fy', 'ltm']);
const ValueKindSchema = z.enum(['amount', 'percent']);
const AmountScaleSchema = z.enum(['ones', 'thousands', 'millions', 'billions']);

const MaterializationSourceApiSchema = z.object({
  file_name: z.string().min(1),
  workbook_hash: z.string().length(64),
  index_id: z.string().min(1),
}).strict();

const EvidenceApiSchema = z.object({
  cell_id: z.string().min(1),
  sheet_name: z.string().min(1),
  cell_coord: z.string().min(1),
  source_text: z.string().min(1),
}).strict().transform((value): BiEvidence => ({
  cellId: value.cell_id,
  sheetName: value.sheet_name,
  cellCoord: value.cell_coord,
  sourceText: value.source_text,
}));

const ObservationApiSchema = z.discriminatedUnion('status', [
  z.object({
    period_id: z.string().min(1),
    status: z.literal('available'),
    raw_value: z.string().nullable(),
    normalized_value: z.string().min(1),
    evidence: z.array(EvidenceApiSchema),
    notes: z.array(z.string()),
  }).strict(),
  z.object({
    period_id: z.string().min(1),
    status: UnavailableStatusSchema,
    raw_value: z.string().nullable(),
    normalized_value: z.null(),
    evidence: z.array(EvidenceApiSchema),
    notes: z.array(z.string()),
    reason: z.string().min(1),
  }).strict(),
]).transform((value): MetricObservation => {
  if (value.status === 'available') {
    return {
      periodId: value.period_id,
      status: value.status,
      rawValue: value.raw_value,
      normalizedValue: value.normalized_value,
      evidence: value.evidence,
      notes: value.notes,
    };
  }
  return {
    periodId: value.period_id,
    status: value.status,
    rawValue: value.raw_value,
    normalizedValue: null,
    evidence: value.evidence,
    notes: value.notes,
    reason: value.reason,
  };
});

const MetricSeriesApiSchema = z.object({
  metric_id: MetricIdSchema,
  label: z.string().min(1),
  value_kind: ValueKindSchema,
  currency: z.string().nullable(),
  scale: AmountScaleSchema.nullable(),
  status: MetricStatusSchema,
  observations: z.array(ObservationApiSchema),
}).strict().transform((value): MetricSeries => ({
  metricId: value.metric_id,
  label: value.label,
  valueKind: value.value_kind,
  currency: value.currency,
  scale: value.scale,
  status: value.status,
  observations: value.observations,
}));

const CompanyListApiSchema = z.object({
  companies: z.array(z.object({
    company_id: z.string().min(1),
    display_name: z.string().min(1),
    source: MaterializationSourceApiSchema.nullable(),
    current_snapshot_id: z.string().nullable(),
    snapshot_status: SnapshotStatusSchema.nullable(),
    refresh_status: RefreshStatusSchema,
    updated_at: z.string().nullable(),
  }).strict()),
}).strict().transform((value): BiCompanyListResponse => ({
  companies: value.companies.map((company) => ({
    companyId: company.company_id,
    displayName: company.display_name,
    source: company.source ? {
      fileName: company.source.file_name,
      workbookHash: company.source.workbook_hash,
      indexId: company.source.index_id,
    } : null,
    currentSnapshotId: company.current_snapshot_id,
    snapshotStatus: company.snapshot_status,
    refreshStatus: company.refresh_status,
    updatedAt: company.updated_at,
  })),
}));

const MaterializationCandidateListApiSchema = z.object({
  candidates: z.array(z.object({
    company_id: z.string().min(1),
    display_name: z.string().min(1),
    source: MaterializationSourceApiSchema,
    reason: z.enum(['not_created', 'source_changed', 'failed']),
  }).strict()),
}).strict().transform((value): BiMaterializationCandidateListResponse => ({
  candidates: value.candidates.map((candidate) => ({
    companyId: candidate.company_id,
    displayName: candidate.display_name,
    source: {
      fileName: candidate.source.file_name,
      workbookHash: candidate.source.workbook_hash,
      indexId: candidate.source.index_id,
    },
    reason: candidate.reason,
  })),
}));

const DashboardApiSchema = z.object({
  schema_version: z.literal(1),
  company: z.object({
    company_id: z.string().min(1),
    display_name: z.string().min(1),
  }).strict(),
  source: MaterializationSourceApiSchema,
  snapshot: z.object({
    snapshot_id: z.string().min(1),
    workbook_hash: z.string().length(64),
    status: SnapshotStatusSchema,
    generated_at: z.string().min(1),
    catalog_version: z.string().min(1),
    formula_version: z.string().min(1),
  }).strict(),
  refresh: z.object({
    status: RefreshStatusSchema,
    job_id: z.string().nullable(),
    started_at: z.string().nullable(),
    message: z.string().nullable(),
  }).strict(),
  periods: z.array(z.object({
    period_id: z.string().min(1),
    kind: PeriodKindSchema,
    label: z.string().min(1),
    source_label: z.string().min(1),
    end_date: z.string().nullable(),
    ordinal: z.number().int(),
  }).strict()),
  metrics: z.partialRecord(MetricIdSchema, MetricSeriesApiSchema),
  issues: z.array(z.object({
    code: z.string().min(1),
    message: z.string().min(1),
    metric_id: MetricIdSchema.nullable(),
  }).strict()),
}).strict().transform((value): BiDashboardSnapshot => ({
  schemaVersion: value.schema_version,
  company: {
    companyId: value.company.company_id,
    displayName: value.company.display_name,
  },
  source: {
    fileName: value.source.file_name,
    workbookHash: value.source.workbook_hash,
    indexId: value.source.index_id,
  },
  snapshot: {
    snapshotId: value.snapshot.snapshot_id,
    workbookHash: value.snapshot.workbook_hash,
    status: value.snapshot.status,
    generatedAt: value.snapshot.generated_at,
    catalogVersion: value.snapshot.catalog_version,
    formulaVersion: value.snapshot.formula_version,
  },
  refresh: {
    status: value.refresh.status,
    jobId: value.refresh.job_id,
    startedAt: value.refresh.started_at,
    message: value.refresh.message,
  },
  periods: value.periods.map((period) => ({
    periodId: period.period_id,
    kind: period.kind,
    label: period.label,
    sourceLabel: period.source_label,
    endDate: period.end_date,
    ordinal: period.ordinal,
  })),
  metrics: value.metrics,
  issues: value.issues.map((issue) => ({
    code: issue.code,
    message: issue.message,
    metricId: issue.metric_id,
  })),
}));

const MaterializationJobApiSchema = z.object({
  job_id: z.string().min(1),
  company_id: z.string().min(1),
  workbook_hash: z.string().length(64),
  status: MaterializationStatusSchema,
  completed_requests: z.number().int().nonnegative(),
  total_requests: z.number().int().nonnegative(),
  published_snapshot_id: z.string().nullable(),
  error_code: z.string().nullable(),
  message: z.string().nullable(),
  started_at: z.string().min(1),
  updated_at: z.string().min(1),
}).strict().transform((value): BiMaterializationJob => ({
  jobId: value.job_id,
  companyId: value.company_id,
  workbookHash: value.workbook_hash,
  status: value.status,
  completedRequests: value.completed_requests,
  totalRequests: value.total_requests,
  publishedSnapshotId: value.published_snapshot_id,
  errorCode: value.error_code,
  message: value.message,
  startedAt: value.started_at,
  updatedAt: value.updated_at,
}));

const MaterializationAcceptedApiSchema = z.object({
  job_id: z.string().min(1),
  status: MaterializationStatusSchema,
  published_snapshot_id: z.string().nullable(),
}).strict().transform((value): BiMaterializationAccepted => ({
  jobId: value.job_id,
  status: value.status,
  publishedSnapshotId: value.published_snapshot_id,
}));

const PendingDashboardApiSchema = z.object({ job: MaterializationJobApiSchema }).strict();

const QuestionJobProgressApiSchema = z.object({
  job_id: z.string().min(1),
  total_questions: z.number().int().nonnegative(),
  queued_questions: z.number().int().nonnegative(),
  running_questions: z.number().int().nonnegative(),
  completed_questions: z.number().int().nonnegative(),
  failed_questions: z.number().int().nonnegative(),
}).strict().transform((value): BiQuestionJobProgress => ({
  jobId: value.job_id,
  totalQuestions: value.total_questions,
  queuedQuestions: value.queued_questions,
  runningQuestions: value.running_questions,
  completedQuestions: value.completed_questions,
  failedQuestions: value.failed_questions,
}));

export function parseBiCompanies(value: unknown): BiCompanyListResponse {
  return CompanyListApiSchema.parse(value);
}

export function parseBiMaterializationCandidates(
  value: unknown,
): BiMaterializationCandidateListResponse {
  return MaterializationCandidateListApiSchema.parse(value);
}

export function parseBiDashboard(value: unknown): BiDashboardSnapshot {
  return DashboardApiSchema.parse(value);
}

export function parseBiPendingDashboard(value: unknown): BiMaterializationJob {
  return PendingDashboardApiSchema.parse(value).job;
}

export function parseBiMaterializationAccepted(value: unknown): BiMaterializationAccepted {
  return MaterializationAcceptedApiSchema.parse(value);
}

export function parseBiMaterializationJob(value: unknown): BiMaterializationJob {
  return MaterializationJobApiSchema.parse(value);
}

export function parseBiQuestionJobProgress(value: unknown): BiQuestionJobProgress {
  return QuestionJobProgressApiSchema.parse(value);
}
