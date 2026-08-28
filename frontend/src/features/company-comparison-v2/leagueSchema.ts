import { z } from 'zod';
import type { FinancialLeagueResponse } from './leagueTypes';

const CandleSchema = z.object({
  year: z.number().int(), period_type: z.enum(['historical', 'forecast']),
  open: z.number(), high: z.number(), low: z.number(), close: z.number(),
  revenue: z.number(), operating_income: z.number(), operating_margin: z.number(),
  evidence_id: z.string().min(1),
}).strict();

const CompanySchema = z.object({
  company_id: z.string().min(1), display_name: z.string().min(1),
  currency: z.string().length(3), scale: z.enum(['ones', 'thousands', 'millions', 'billions']),
  rank: z.number().int().positive(), previous_rank: z.number().int().positive(), rank_change: z.number().int(),
  composite_score: z.number().min(0).max(100), growth_score: z.number().min(0).max(100),
  profitability_score: z.number().min(0).max(100), stability_score: z.number().min(0).max(100),
  revenue_cagr: z.number(), operating_margin: z.number(), liabilities_to_assets: z.number(),
  net_debt: z.number(), net_debt_to_revenue: z.number(),
  tier: z.enum(['S', 'A', 'B', 'C']), candles: z.array(CandleSchema).length(8),
}).strict();

const EvidenceSchema = z.object({
  evidence_id: z.string(), company_id: z.string(), file_name: z.string(), sheet_name: z.string(),
  cell_coord: z.string(), source_text: z.string(), origin: z.enum(['snapshot', 'rag']),
}).strict();

const BucketSchema = z.object({ label: z.string(), count: z.number().int().nonnegative() }).strict();

const LeagueSchema = z.object({
  schema_version: z.literal(1), generated_at: z.string(), historical_end_year: z.literal(2025),
  companies: z.array(CompanySchema).min(15).max(30),
  spotlight: z.object({
    leader_company_id: z.string(), riser_company_id: z.string(), average_cagr: z.number(),
    average_margin: z.number(), cagr_distribution: z.array(BucketSchema), margin_distribution: z.array(BucketSchema),
  }).strict(),
  evidence: z.array(EvidenceSchema),
}).strict();

export function parseFinancialLeague(value: unknown): FinancialLeagueResponse {
  const data = LeagueSchema.parse(value);
  return {
    schemaVersion: data.schema_version,
    generatedAt: data.generated_at,
    historicalEndYear: data.historical_end_year,
    companies: data.companies.map((company) => ({
      companyId: company.company_id, displayName: company.display_name,
      currency: company.currency, scale: company.scale, rank: company.rank,
      previousRank: company.previous_rank, rankChange: company.rank_change,
      compositeScore: company.composite_score, growthScore: company.growth_score,
      profitabilityScore: company.profitability_score, stabilityScore: company.stability_score,
      revenueCagr: company.revenue_cagr, operatingMargin: company.operating_margin,
      liabilitiesToAssets: company.liabilities_to_assets, netDebt: company.net_debt,
      netDebtToRevenue: company.net_debt_to_revenue,
      tier: company.tier,
      candles: company.candles.map((candle) => ({
        year: candle.year, periodType: candle.period_type, open: candle.open, high: candle.high,
        low: candle.low, close: candle.close, revenue: candle.revenue,
        operatingIncome: candle.operating_income, operatingMargin: candle.operating_margin,
        evidenceId: candle.evidence_id,
      })),
    })),
    spotlight: {
      leaderCompanyId: data.spotlight.leader_company_id, riserCompanyId: data.spotlight.riser_company_id,
      averageCagr: data.spotlight.average_cagr, averageMargin: data.spotlight.average_margin,
      cagrDistribution: data.spotlight.cagr_distribution, marginDistribution: data.spotlight.margin_distribution,
    },
    evidence: data.evidence.map((item) => ({
      evidenceId: item.evidence_id, companyId: item.company_id, fileName: item.file_name,
      sheetName: item.sheet_name, cellCoord: item.cell_coord, sourceText: item.source_text, origin: item.origin,
    })),
  };
}
