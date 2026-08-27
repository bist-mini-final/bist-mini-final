export interface CompanyComparisonV2Request {
  readonly companyIds: readonly string[];
  readonly startYear: number;
  readonly endYear: number;
  readonly question?: string;
}

export type ComparisonEvaluationType = 'growth' | 'profitability' | 'stability' | 'comprehensive';
export type ComparisonChartId = 'revenue_trend' | 'operating_income_trend' | 'growth_profitability' | 'stability';

export interface ComparisonV2QueryAnalysis {
  readonly question: string;
  readonly evaluationType: ComparisonEvaluationType;
  readonly evaluationLabel: string;
  readonly rationale: string;
  readonly requiredMetrics: readonly string[];
  readonly chartIds: readonly ComparisonChartId[];
}

export interface ComparisonV2Point {
  readonly year: number;
  readonly revenue: number;
  readonly operatingIncome: number;
}

export interface ComparisonV2Company {
  readonly companyId: string;
  readonly displayName: string;
  readonly currency: string;
  readonly scale: 'ones' | 'thousands' | 'millions' | 'billions';
  readonly points: readonly ComparisonV2Point[];
  readonly revenueCagr: number;
  readonly operatingMargin: number;
  readonly liabilitiesToAssets: number;
  readonly netDebt: number;
  readonly stabilityBasisYear: number;
}

export interface ComparisonV2BriefSection {
  readonly title: string;
  readonly body: string;
  readonly evidenceIds: readonly string[];
}

export interface CompanyComparisonV2Brief {
  readonly comparedCompanyIds: readonly string[];
  readonly growth: ComparisonV2BriefSection;
  readonly profitability: ComparisonV2BriefSection;
  readonly risk: ComparisonV2BriefSection;
  readonly caveats: readonly string[];
}

export interface ComparisonV2Evidence {
  readonly evidenceId: string;
  readonly companyId: string;
  readonly fileName: string;
  readonly sheetName: string;
  readonly cellCoord: string;
  readonly sourceText: string;
  readonly origin: 'snapshot' | 'rag';
}

export interface CompanyComparisonV2Response {
  readonly schemaVersion: 2;
  readonly analysisId: string;
  readonly briefStatus: 'ready' | 'failed';
  readonly startYear: number;
  readonly endYear: number;
  readonly queryAnalysis: ComparisonV2QueryAnalysis | null;
  readonly companies: readonly ComparisonV2Company[];
  readonly brief: CompanyComparisonV2Brief | null;
  readonly evidence: readonly ComparisonV2Evidence[];
  readonly warnings: readonly string[];
  readonly meta: {
    readonly generatedAt: string;
    readonly evidenceCount: number;
    readonly latencyMs: number;
    readonly cacheHit: boolean;
  };
}
