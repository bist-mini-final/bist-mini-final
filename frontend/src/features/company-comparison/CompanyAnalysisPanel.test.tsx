import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { CompanyAnalysisPanel } from './CompanyAnalysisPanel';
import type { ComparisonCompany } from './types';

function company(
  companyId: string,
  rank: number,
  score: number,
): ComparisonCompany {
  return {
    companyId,
    displayName: companyId,
    currency: 'USD',
    scale: 'millions',
    sourceSnapshotId: `snapshot-${companyId}`,
    historicalStartYear: 2023,
    historicalEndYear: 2024,
    rank,
    previousRank: rank,
    rankChange: 0,
    compositeScore: score,
    growthScore: score,
    profitabilityScore: score - 2,
    stabilityScore: score - 4,
    revenueCagr: score / 10,
    operatingMargin: score / 8,
    liabilitiesToAssets: 45,
    netDebt: 100,
    netDebtToRevenue: 0.1,
    tier: rank === 1 ? 'S' : 'A',
    periods: [
      {
        year: 2023,
        periodType: 'historical',
        revenue: 100,
        operatingIncome: 10,
        operatingMargin: 10,
        evidenceIds: [],
        assumptionId: null,
      },
      {
        year: 2024,
        periodType: 'historical',
        revenue: 120,
        operatingIncome: 14,
        operatingMargin: 11.7,
        evidenceIds: [],
        assumptionId: null,
      },
    ],
  };
}

const first = company('AmeSoft', 1, 92);
const second = company('Nexora Labs', 2, 84);
const common = {
  companies: [first, second],
  officialRankByCompanyId: new Map([[first.companyId, 1], [second.companyId, 2]]),
  analysisCompany: first,
  analysisPeriods: [...first.periods],
  analysisForecastPeriods: [],
  analysisReasons: ['성장성이 종합순위에 가장 크게 기여했습니다.'],
  averageCagr: 8,
  averageMargin: 10,
  averageDebtRatio: 50,
};

describe('CompanyAnalysisPanel', () => {
  it('renders focused-company insight independently from the page shell', () => {
    render(
      <CompanyAnalysisPanel
        comparison={{
          ...common,
          comparisonCompanies: [],
          comparisonPeriods: [],
        }}
        assumptions={[]}
      />,
    );

    expect(screen.getByText('선택 기업 분석')).toBeInTheDocument();
    expect(screen.getByText('AmeSoft')).toBeInTheDocument();
    expect(screen.getByText('성장성이 종합순위에 가장 크게 기여했습니다.')).toBeInTheDocument();
  });

  it('switches to the two-company comparison presentation', () => {
    render(
      <CompanyAnalysisPanel
        comparison={{
          ...common,
          comparisonCompanies: [first, second],
          comparisonPeriods: [[...first.periods], [...second.periods]],
        }}
        assumptions={[]}
      />,
    );

    expect(screen.getByText('COMPARE MODE')).toBeInTheDocument();
    expect(screen.getByText('선택 기업 비교')).toBeInTheDocument();
    expect(screen.getByText('A AmeSoft')).toBeInTheDocument();
    expect(screen.getByText('B Nexora Labs')).toBeInTheDocument();
    expect(screen.getByText('종합점수 구성 비교')).toBeInTheDocument();
    expect(screen.getByText('공통 0~100점 기준')).toBeInTheDocument();
    expect(screen.getAllByText('A +8.0점')).toHaveLength(3);
    expect(screen.getByLabelText('A AmeSoft, 성장성 92.0점, CAGR 9.2%')).toBeInTheDocument();
    expect(screen.getByLabelText('B Nexora Labs, 안정성 80.0점, 부채 45.0% · 순부채/매출 0.1%')).toBeInTheDocument();
  });
});
