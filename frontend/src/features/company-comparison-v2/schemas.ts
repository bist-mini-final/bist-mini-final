import { z } from 'zod';
import type { CompanyComparisonV2Response } from './types';

const PointSchema = z.object({
  year: z.number().int(),
  revenue: z.number(),
  operating_income: z.number(),
}).strict();

const CompanySchema = z.object({
  company_id: z.string().min(1),
  display_name: z.string().min(1),
  currency: z.string().length(3),
  scale: z.enum(['ones', 'thousands', 'millions', 'billions']),
  points: z.array(PointSchema).min(2),
  revenue_cagr: z.number(),
  operating_margin: z.number(),
  liabilities_to_assets: z.number(),
  net_debt: z.number(),
  stability_basis_year: z.number().int(),
}).strict();

const BriefSectionSchema = z.object({
  title: z.string().min(1),
  body: z.string().min(1),
  evidence_ids: z.array(z.string().min(1)).min(1),
}).strict();

const BriefSchema = z.object({
  compared_company_ids: z.array(z.string().min(1)).min(2).max(3),
  growth: BriefSectionSchema,
  profitability: BriefSectionSchema,
  risk: BriefSectionSchema,
  caveats: z.array(z.string()),
}).strict();

const EvidenceSchema = z.object({
  evidence_id: z.string().min(1),
  company_id: z.string().min(1),
  file_name: z.string().min(1),
  sheet_name: z.string().min(1),
  cell_coord: z.string().min(1),
  source_text: z.string().min(1),
  origin: z.enum(['snapshot', 'rag']),
}).strict();

const QueryAnalysisSchema = z.object({
  question: z.string().min(5),
  evaluation_type: z.enum(['growth', 'profitability', 'stability', 'comprehensive']),
  evaluation_label: z.string().min(1),
  rationale: z.string().min(10),
  required_metrics: z.array(z.string().min(1)).min(1),
  chart_ids: z.array(z.enum(['revenue_trend', 'operating_income_trend', 'growth_profitability', 'stability'])).min(1),
}).strict();

const ResponseSchema = z.object({
  schema_version: z.literal(2),
  analysis_id: z.string().min(1),
  analysis_mode: z.literal('rag'),
  brief_status: z.enum(['ready', 'failed']),
  start_year: z.number().int(),
  end_year: z.number().int(),
  query_analysis: QueryAnalysisSchema.nullable(),
  companies: z.array(CompanySchema).min(2).max(3),
  brief: BriefSchema.nullable(),
  evidence: z.array(EvidenceSchema),
  warnings: z.array(z.string()),
  meta: z.object({
    generated_at: z.string().min(1),
    snapshot_ids: z.array(z.string()),
    evidence_count: z.number().int().nonnegative(),
    prompt_version: z.string().min(1),
    model: z.string().min(1),
    latency_ms: z.number().int().nonnegative(),
    cache_hit: z.boolean(),
  }).strict(),
}).strict();

export function parseCompanyComparisonV2(value: unknown): CompanyComparisonV2Response {
  const parsed = ResponseSchema.parse(value);
  return {
    schemaVersion: parsed.schema_version,
    analysisId: parsed.analysis_id,
    briefStatus: parsed.brief_status,
    startYear: parsed.start_year,
    endYear: parsed.end_year,
    queryAnalysis: parsed.query_analysis ? {
      question: parsed.query_analysis.question,
      evaluationType: parsed.query_analysis.evaluation_type,
      evaluationLabel: parsed.query_analysis.evaluation_label,
      rationale: parsed.query_analysis.rationale,
      requiredMetrics: parsed.query_analysis.required_metrics,
      chartIds: parsed.query_analysis.chart_ids,
    } : null,
    companies: parsed.companies.map((company) => ({
      companyId: company.company_id,
      displayName: company.display_name,
      currency: company.currency,
      scale: company.scale,
      points: company.points.map((point) => ({
        year: point.year,
        revenue: point.revenue,
        operatingIncome: point.operating_income,
      })),
      revenueCagr: company.revenue_cagr,
      operatingMargin: company.operating_margin,
      liabilitiesToAssets: company.liabilities_to_assets,
      netDebt: company.net_debt,
      stabilityBasisYear: company.stability_basis_year,
    })),
    brief: parsed.brief ? {
      comparedCompanyIds: parsed.brief.compared_company_ids,
      growth: {
        title: parsed.brief.growth.title,
        body: parsed.brief.growth.body,
        evidenceIds: parsed.brief.growth.evidence_ids,
      },
      profitability: {
        title: parsed.brief.profitability.title,
        body: parsed.brief.profitability.body,
        evidenceIds: parsed.brief.profitability.evidence_ids,
      },
      risk: {
        title: parsed.brief.risk.title,
        body: parsed.brief.risk.body,
        evidenceIds: parsed.brief.risk.evidence_ids,
      },
      caveats: parsed.brief.caveats,
    } : null,
    evidence: parsed.evidence.map((item) => ({
      evidenceId: item.evidence_id,
      companyId: item.company_id,
      fileName: item.file_name,
      sheetName: item.sheet_name,
      cellCoord: item.cell_coord,
      sourceText: item.source_text,
      origin: item.origin,
    })),
    warnings: parsed.warnings,
    meta: {
      generatedAt: parsed.meta.generated_at,
      evidenceCount: parsed.meta.evidence_count,
      latencyMs: parsed.meta.latency_ms,
      cacheHit: parsed.meta.cache_hit,
    },
  };
}
