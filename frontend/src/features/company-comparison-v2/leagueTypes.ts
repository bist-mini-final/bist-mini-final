export type FinancialTier = 'S' | 'A' | 'B' | 'C';

export interface FinancialCandle {
  readonly year: number;
  readonly periodType: 'historical' | 'forecast';
  readonly open: number;
  readonly high: number;
  readonly low: number;
  readonly close: number;
  readonly revenue: number;
  readonly operatingIncome: number;
  readonly operatingMargin: number;
  readonly evidenceId: string;
}

export interface LeagueCompany {
  readonly companyId: string;
  readonly displayName: string;
  readonly currency: string;
  readonly scale: 'ones' | 'thousands' | 'millions' | 'billions';
  readonly rank: number;
  readonly previousRank: number;
  readonly rankChange: number;
  readonly compositeScore: number;
  readonly growthScore: number;
  readonly profitabilityScore: number;
  readonly stabilityScore: number;
  readonly revenueCagr: number;
  readonly operatingMargin: number;
  readonly liabilitiesToAssets: number;
  readonly netDebt: number;
  readonly tier: FinancialTier;
  readonly candles: readonly FinancialCandle[];
}

export interface LeagueEvidence {
  readonly evidenceId: string;
  readonly companyId: string;
  readonly fileName: string;
  readonly sheetName: string;
  readonly cellCoord: string;
  readonly sourceText: string;
  readonly origin: 'snapshot' | 'rag';
}

export interface LeagueDistributionBucket {
  readonly label: string;
  readonly count: number;
}

export interface FinancialLeagueResponse {
  readonly schemaVersion: 1;
  readonly generatedAt: string;
  readonly historicalEndYear: 2025;
  readonly companies: readonly LeagueCompany[];
  readonly spotlight: {
    readonly leaderCompanyId: string;
    readonly riserCompanyId: string;
    readonly averageCagr: number;
    readonly averageMargin: number;
    readonly cagrDistribution: readonly LeagueDistributionBucket[];
    readonly marginDistribution: readonly LeagueDistributionBucket[];
  };
  readonly evidence: readonly LeagueEvidence[];
}
