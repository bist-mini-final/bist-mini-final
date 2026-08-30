import { useCallback, useMemo, useState } from 'react';
import type { BenchmarkScatterPoint } from './CompanyComparisonCharts';
import { forecastPeriods, historicalPeriods, rankReason } from './analysis';
import {
  RANKING_METRICS,
  orderForDisplay,
  rankCompaniesByComposite,
  rankCompaniesByMetric,
  toggleCompanySelection,
  type DisplayDirection,
  type RankingMetric,
} from './metricRanking';
import type { ComparisonCompany } from './types';
import { useCompanyComparisonSnapshot } from './useCompanyComparisonSnapshot';

/** Owns snapshot loading, ranking controls, company selection, and derived chart data. */
export function useCompanyComparisonController() {
  const [reloadKey, setReloadKey] = useState(0);
  const state = useCompanyComparisonSnapshot(reloadKey);
  const [rankingMetric, setRankingMetric] = useState<RankingMetric>('composite');
  const [displayDirection, setDisplayDirection] = useState<DisplayDirection>('best-first');
  const [selectedCompanyIds, setSelectedCompanyIds] = useState<ReadonlySet<string>>(new Set());
  const [focusedCompanyId, setFocusedCompanyId] = useState('');

  const companies = useMemo(
    () => state.status === 'ready' ? state.data.companies : [],
    [state],
  );
  const officialRankedCompanies = useMemo(
    () => rankCompaniesByComposite(companies),
    [companies],
  );
  const activeMetricRankedCompanies = useMemo(
    () => rankCompaniesByMetric(companies, rankingMetric),
    [companies, rankingMetric],
  );
  const displayedCompanies = useMemo(
    () => orderForDisplay(activeMetricRankedCompanies, rankingMetric, displayDirection),
    [activeMetricRankedCompanies, displayDirection, rankingMetric],
  );
  const officialRankByCompanyId = useMemo(
    () => new Map(officialRankedCompanies.map(({ company, rank }) => [company.companyId, rank])),
    [officialRankedCompanies],
  );
  const selectedCompanies = useMemo(
    () => Array.from(selectedCompanyIds)
      .map((companyId) => companies.find((company) => company.companyId === companyId))
      .filter((company): company is ComparisonCompany => Boolean(company)),
    [companies, selectedCompanyIds],
  );
  const focusedCompany = useMemo(
    () => companies.find((company) => company.companyId === focusedCompanyId),
    [companies, focusedCompanyId],
  );
  const analysisCompany = selectedCompanies.length === 1
    ? selectedCompanies[0]
    : focusedCompany ?? officialRankedCompanies[0]?.company;
  const comparisonCompanies = useMemo(
    () => selectedCompanies.length === 2 ? selectedCompanies : [],
    [selectedCompanies],
  );
  const analysisPeriods = useMemo(
    () => analysisCompany ? historicalPeriods(analysisCompany) : [],
    [analysisCompany],
  );
  const analysisForecastPeriods = useMemo(
    () => analysisCompany ? forecastPeriods(analysisCompany) : [],
    [analysisCompany],
  );
  const comparisonPeriods = useMemo(
    () => comparisonCompanies.map(historicalPeriods),
    [comparisonCompanies],
  );
  const analysisReasons = useMemo(
    () => analysisCompany ? rankReason(analysisCompany, companies) : [],
    [analysisCompany, companies],
  );

  const averageCagr = state.status === 'ready' ? state.data.spotlight.averageCagr : 0;
  const averageMargin = state.status === 'ready' ? state.data.spotlight.averageMargin : 0;
  const averageDebtRatio = state.status === 'ready'
    ? state.data.spotlight.averageLiabilitiesToAssets
    : 0;
  const benchmarkScatterData = useMemo<readonly BenchmarkScatterPoint[]>(
    () => companies.map((company) => ({
      companyId: company.companyId,
      companyName: company.displayName,
      growth: company.revenueCagr,
      margin: company.operatingMargin,
      tone: comparisonCompanies[0]?.companyId === company.companyId
        ? 'compare-a'
        : comparisonCompanies[1]?.companyId === company.companyId
          ? 'compare-b'
          : analysisCompany?.companyId === company.companyId
            ? 'selected'
            : 'default',
    })),
    [analysisCompany?.companyId, companies, comparisonCompanies],
  );

  const selectRankingMetric = useCallback((metric: RankingMetric) => {
    if (rankingMetric === metric) {
      setDisplayDirection((current) => current === 'best-first' ? 'worst-first' : 'best-first');
      return;
    }
    setRankingMetric(metric);
    setDisplayDirection('best-first');
  }, [rankingMetric]);

  const resetRanking = useCallback(() => {
    setRankingMetric('composite');
    setDisplayDirection('best-first');
  }, []);

  const toggleCompany = useCallback((companyId: string) => {
    if (!selectedCompanyIds.has(companyId)) setFocusedCompanyId(companyId);
    setSelectedCompanyIds((current) => toggleCompanySelection(current, companyId));
  }, [selectedCompanyIds]);

  const refresh = useCallback(() => setReloadKey((key) => key + 1), []);

  return {
    state,
    companies,
    rankingMetric,
    displayDirection,
    selectedCompanyIds,
    focusedCompanyId,
    displayedCompanies,
    officialRankByCompanyId,
    analysisCompany,
    comparisonCompanies,
    analysisPeriods,
    analysisForecastPeriods,
    comparisonPeriods,
    analysisReasons,
    averageCagr,
    averageMargin,
    averageDebtRatio,
    benchmarkScatterData,
    activeRankingLabel: `${RANKING_METRICS[rankingMetric].label} 순위`,
    metricDirectionLabel: displayDirection === 'best-first' ? '높은 순' : '낮은 순',
    selectRankingMetric,
    resetRanking,
    refresh,
    focusCompany: setFocusedCompanyId,
    toggleCompany,
  };
}

export type CompanyComparisonController = ReturnType<typeof useCompanyComparisonController>;
