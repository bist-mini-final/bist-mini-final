import type { CompanyBrandMark } from '../../shared/company-brand/contract';

export type FinancialTier = 'S' | 'A' | 'B' | 'C';

export interface ComparisonPeriod {
  readonly year: number;
  readonly periodType: 'historical' | 'forecast';
  readonly revenue: number;
  readonly operatingIncome: number;
  readonly operatingMargin: number;
  readonly evidenceIds: readonly string[];
  readonly assumptionId: string | null;
}

export interface ComparisonCompany {
  readonly companyId: string;
  readonly displayName: string;
  readonly brandMark?: CompanyBrandMark | null;
  readonly currency: string;
  readonly scale: 'ones' | 'thousands' | 'millions' | 'billions';
  readonly sourceSnapshotId: string;
  readonly historicalStartYear: number;
  readonly historicalEndYear: number;
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
  readonly netDebtToRevenue: number;
  readonly tier: FinancialTier;
  readonly periods: readonly ComparisonPeriod[];
}

export interface ComparisonEvidence {
  readonly evidenceId: string;
  readonly companyId: string;
  readonly metricId: string;
  readonly year: number | null;
  readonly fileName: string;
  readonly sheetName: string;
  readonly cellCoord: string;
  readonly sourceText: string;
  readonly origin: 'bi_snapshot';
}

export interface ComparisonDistributionBucket {
  readonly label: string;
  readonly count: number;
}

export interface CompanyComparisonSnapshot {
  readonly schemaVersion: 1;
  readonly snapshot: {
    readonly snapshotId: string;
    readonly status: 'ready' | 'partial';
    readonly generatedAt: string;
    readonly sourceFingerprint: string;
    readonly sourceSnapshotIds: readonly string[];
    readonly scoringVersion: string;
    readonly forecastVersion: string;
  };
  readonly historicalStartYear: number;
  readonly historicalEndYear: number;
  readonly forecastEndYear: number;
  readonly companies: readonly ComparisonCompany[];
  readonly spotlight: {
    readonly leaderCompanyId: string;
    readonly riserCompanyId: string;
    readonly averageCagr: number;
    readonly averageMargin: number;
    readonly averageLiabilitiesToAssets: number;
    readonly cagrDistribution: readonly ComparisonDistributionBucket[];
    readonly marginDistribution: readonly ComparisonDistributionBucket[];
  };
  readonly evidence: readonly ComparisonEvidence[];
  readonly exclusions: readonly {
    readonly companyId: string;
    readonly displayName: string;
    readonly reasons: readonly string[];
  }[];
  readonly assumptions: readonly {
    readonly assumptionId: string;
    readonly description: string;
  }[];
}
