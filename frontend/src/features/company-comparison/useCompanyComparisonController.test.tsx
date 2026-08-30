import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ComparisonCompany, CompanyComparisonSnapshot } from './types';
import { useCompanyComparisonSnapshot } from './useCompanyComparisonSnapshot';
import { useCompanyComparisonController } from './useCompanyComparisonController';

vi.mock('./useCompanyComparisonSnapshot', () => ({
  useCompanyComparisonSnapshot: vi.fn(),
}));

function company(
  companyId: string,
  rank: number,
  compositeScore: number,
  revenueCagr: number,
): ComparisonCompany {
  return {
    companyId,
    displayName: companyId.toUpperCase(),
    currency: 'USD',
    scale: 'millions',
    sourceSnapshotId: `snapshot-${companyId}`,
    historicalStartYear: 2023,
    historicalEndYear: 2024,
    rank,
    previousRank: rank,
    rankChange: 0,
    compositeScore,
    growthScore: revenueCagr * 5,
    profitabilityScore: 70,
    stabilityScore: 65,
    revenueCagr,
    operatingMargin: 15,
    liabilitiesToAssets: 40,
    netDebt: 100,
    netDebtToRevenue: 0.1,
    tier: 'A',
    periods: [
      {
        year: 2023,
        periodType: 'historical',
        revenue: 100,
        operatingIncome: 15,
        operatingMargin: 15,
        evidenceIds: [],
        assumptionId: null,
      },
      {
        year: 2024,
        periodType: 'historical',
        revenue: 100 + revenueCagr,
        operatingIncome: 16,
        operatingMargin: 15,
        evidenceIds: [],
        assumptionId: null,
      },
    ],
  };
}

const snapshot: CompanyComparisonSnapshot = {
  schemaVersion: 1,
  snapshot: {
    snapshotId: 'comparison-1',
    status: 'ready',
    generatedAt: '2026-08-30T00:00:00Z',
    sourceFingerprint: 'fingerprint',
    sourceSnapshotIds: ['snapshot-a', 'snapshot-b', 'snapshot-c'],
    scoringVersion: '1',
    forecastVersion: '1',
  },
  historicalStartYear: 2023,
  historicalEndYear: 2024,
  forecastEndYear: 2025,
  companies: [
    company('a', 2, 80, 8),
    company('b', 1, 90, 4),
    company('c', 3, 70, 12),
  ],
  spotlight: {
    leaderCompanyId: 'b',
    riserCompanyId: 'c',
    averageCagr: 8,
    averageMargin: 15,
    averageLiabilitiesToAssets: 40,
    cagrDistribution: [],
    marginDistribution: [],
  },
  evidence: [],
  exclusions: [],
  assumptions: [],
};

describe('useCompanyComparisonController', () => {
  beforeEach(() => {
    vi.mocked(useCompanyComparisonSnapshot).mockReturnValue({
      status: 'ready',
      data: snapshot,
    });
  });

  it('derives the official leader and toggles ranking direction', () => {
    const { result } = renderHook(() => useCompanyComparisonController());

    expect(result.current.analysisCompany?.companyId).toBe('b');
    expect(result.current.displayedCompanies.map(({ company: item }) => item.companyId))
      .toEqual(['b', 'a', 'c']);

    act(() => result.current.selectRankingMetric('revenueCagr'));
    expect(result.current.rankingMetric).toBe('revenueCagr');
    expect(result.current.displayedCompanies.map(({ company: item }) => item.companyId))
      .toEqual(['c', 'a', 'b']);

    act(() => result.current.selectRankingMetric('revenueCagr'));
    expect(result.current.displayDirection).toBe('worst-first');
    expect(result.current.displayedCompanies.map(({ company: item }) => item.companyId))
      .toEqual(['b', 'a', 'c']);
  });

  it('caps comparison selection at two companies and refreshes through the snapshot hook', () => {
    const { result } = renderHook(() => useCompanyComparisonController());

    act(() => result.current.toggleCompany('a'));
    act(() => result.current.toggleCompany('b'));
    act(() => result.current.toggleCompany('c'));

    expect([...result.current.selectedCompanyIds]).toEqual(['b', 'c']);
    expect(result.current.comparisonCompanies.map((item) => item.companyId)).toEqual(['b', 'c']);
    expect(result.current.focusedCompanyId).toBe('c');

    act(() => result.current.refresh());
    expect(useCompanyComparisonSnapshot).toHaveBeenLastCalledWith(1);
  });
});
