import { z } from 'zod';
import { CompanyBrandMarkApiSchema } from '../../shared/company-brand/schema';
import type { CompanyComparisonSnapshot } from './types';

const PeriodSchema = z.object({
  year: z.number().int(),
  period_type: z.enum(['historical', 'forecast']),
  revenue: z.number(),
  operating_income: z.number(),
  operating_margin: z.number(),
  evidence_ids: z.array(z.string().min(1)).min(1),
  assumption_id: z.string().nullable(),
}).strict();

const CompanySchema = z.object({
  company_id: z.string().min(1),
  display_name: z.string().min(1),
  brand_mark: CompanyBrandMarkApiSchema.nullable().optional(),
  currency: z.string().length(3),
  scale: z.enum(['ones', 'thousands', 'millions', 'billions']),
  source_snapshot_id: z.string().min(1),
  historical_start_year: z.number().int(),
  historical_end_year: z.number().int(),
  rank: z.number().int().positive(),
  previous_rank: z.number().int().positive(),
  rank_change: z.number().int(),
  composite_score: z.number().min(0).max(100),
  growth_score: z.number().min(0).max(100),
  profitability_score: z.number().min(0).max(100),
  stability_score: z.number().min(0).max(100),
  revenue_cagr: z.number(),
  operating_margin: z.number(),
  liabilities_to_assets: z.number(),
  net_debt: z.number(),
  net_debt_to_revenue: z.number(),
  tier: z.enum(['S', 'A', 'B', 'C']),
  periods: z.array(PeriodSchema).min(5).max(8),
}).strict();

const EvidenceSchema = z.object({
  evidence_id: z.string().min(1),
  company_id: z.string().min(1),
  metric_id: z.string().min(1),
  year: z.number().int().nullable(),
  file_name: z.string().min(1),
  sheet_name: z.string().min(1),
  cell_coord: z.string().min(1),
  source_text: z.string().min(1),
  origin: z.literal('bi_snapshot'),
}).strict();

const BucketSchema = z.object({
  label: z.string(),
  count: z.number().int().nonnegative(),
}).strict();

const SnapshotSchema = z.object({
  schema_version: z.literal(1),
  snapshot: z.object({
    snapshot_id: z.string().min(1),
    status: z.enum(['ready', 'partial']),
    generated_at: z.string(),
    source_fingerprint: z.string().length(64),
    source_snapshot_ids: z.array(z.string().min(1)).min(2).max(30),
    scoring_version: z.string().min(1),
    forecast_version: z.string().min(1),
  }).strict(),
  historical_start_year: z.number().int(),
  historical_end_year: z.number().int(),
  forecast_end_year: z.number().int(),
  companies: z.array(CompanySchema).min(2).max(30),
  spotlight: z.object({
    leader_company_id: z.string(),
    riser_company_id: z.string(),
    average_cagr: z.number(),
    average_margin: z.number(),
    average_liabilities_to_assets: z.number(),
    cagr_distribution: z.array(BucketSchema),
    margin_distribution: z.array(BucketSchema),
  }).strict(),
  evidence: z.array(EvidenceSchema),
  exclusions: z.array(z.object({
    company_id: z.string(),
    display_name: z.string(),
    reasons: z.array(z.string()).min(1),
  }).strict()),
  assumptions: z.array(z.object({
    assumption_id: z.string(),
    description: z.string(),
  }).strict()),
}).strict();

export function parseCompanyComparisonSnapshot(value: unknown): CompanyComparisonSnapshot {
  const data = SnapshotSchema.parse(value);
  return {
    schemaVersion: data.schema_version,
    snapshot: {
      snapshotId: data.snapshot.snapshot_id,
      status: data.snapshot.status,
      generatedAt: data.snapshot.generated_at,
      sourceFingerprint: data.snapshot.source_fingerprint,
      sourceSnapshotIds: data.snapshot.source_snapshot_ids,
      scoringVersion: data.snapshot.scoring_version,
      forecastVersion: data.snapshot.forecast_version,
    },
    historicalStartYear: data.historical_start_year,
    historicalEndYear: data.historical_end_year,
    forecastEndYear: data.forecast_end_year,
    companies: data.companies.map((company) => ({
      companyId: company.company_id,
      displayName: company.display_name,
      brandMark: company.brand_mark,
      currency: company.currency,
      scale: company.scale,
      sourceSnapshotId: company.source_snapshot_id,
      historicalStartYear: company.historical_start_year,
      historicalEndYear: company.historical_end_year,
      rank: company.rank,
      previousRank: company.previous_rank,
      rankChange: company.rank_change,
      compositeScore: company.composite_score,
      growthScore: company.growth_score,
      profitabilityScore: company.profitability_score,
      stabilityScore: company.stability_score,
      revenueCagr: company.revenue_cagr,
      operatingMargin: company.operating_margin,
      liabilitiesToAssets: company.liabilities_to_assets,
      netDebt: company.net_debt,
      netDebtToRevenue: company.net_debt_to_revenue,
      tier: company.tier,
      periods: company.periods.map((period) => ({
        year: period.year,
        periodType: period.period_type,
        revenue: period.revenue,
        operatingIncome: period.operating_income,
        operatingMargin: period.operating_margin,
        evidenceIds: period.evidence_ids,
        assumptionId: period.assumption_id,
      })),
    })),
    spotlight: {
      leaderCompanyId: data.spotlight.leader_company_id,
      riserCompanyId: data.spotlight.riser_company_id,
      averageCagr: data.spotlight.average_cagr,
      averageMargin: data.spotlight.average_margin,
      averageLiabilitiesToAssets: data.spotlight.average_liabilities_to_assets,
      cagrDistribution: data.spotlight.cagr_distribution,
      marginDistribution: data.spotlight.margin_distribution,
    },
    evidence: data.evidence.map((item) => ({
      evidenceId: item.evidence_id,
      companyId: item.company_id,
      metricId: item.metric_id,
      year: item.year,
      fileName: item.file_name,
      sheetName: item.sheet_name,
      cellCoord: item.cell_coord,
      sourceText: item.source_text,
      origin: item.origin,
    })),
    exclusions: data.exclusions.map((item) => ({
      companyId: item.company_id,
      displayName: item.display_name,
      reasons: item.reasons,
    })),
    assumptions: data.assumptions.map((item) => ({
      assumptionId: item.assumption_id,
      description: item.description,
    })),
  };
}
