import {
  AlertCircle,
  ArrowUpDown,
  ChevronDown,
  Clock,
  Database,
  RefreshCw,
  X,
} from 'lucide-react';
import { useMemo, useState } from 'react';
import {
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { AppLink } from '../app/router';
import { Button } from '../shared/ui';
import { CompanyLogoBadge } from '../features/company-comparison/CompanyLogoBadge';
import {
  BenchmarkScatterTooltip,
  ComparisonTrendChart,
  FinancialTrendChart,
  renderBenchmarkScatterMarker,
  type BenchmarkScatterPoint,
} from '../features/company-comparison/CompanyComparisonCharts';
import {
  formatAmount,
  forecastPeriods,
  historicalPeriods,
  indexedSeries,
  percentChange,
  rankReason,
  SCORE_DIMENSIONS,
  scoreRank,
  signedPoint,
} from '../features/company-comparison/analysis';
import {
  RANKING_METRICS,
  latestHistoricalPeriod,
  orderForDisplay,
  rankCompaniesByComposite,
  rankCompaniesByMetric,
  toggleCompanySelection,
  type DisplayDirection,
  type RankingMetric,
} from '../features/company-comparison/metricRanking';
import { useCompanyComparisonSnapshot } from '../features/company-comparison/useCompanyComparisonSnapshot';
import type { ComparisonCompany } from '../features/company-comparison/types';
import '../features/company-comparison/company-comparison.css';

const FACTOR_LABELS: Record<'Overall' | 'Revenue' | 'Profit' | 'Growth', string> = {
  Overall: '종합순위',
  Revenue: '매출액',
  Profit: '영업이익',
  Growth: '성장률',
};

export function CompanyComparisonPage() {
  const [reloadKey, setReloadKey] = useState(0);
  const state = useCompanyComparisonSnapshot(reloadKey);

  const [rankingMetric, setRankingMetric] = useState<RankingMetric>('composite');
  const [displayDirection, setDisplayDirection] = useState<DisplayDirection>('best-first');
  const [selectedCompanyIds, setSelectedCompanyIds] = useState<ReadonlySet<string>>(new Set());
  const [focusedCompanyId, setFocusedCompanyId] = useState<string>('');

  const companiesList = useMemo(() => {
    if (state.status !== 'ready') return [];
    return state.data.companies;
  }, [state]);

  const filteredCompanies = companiesList;

  const officialRankedCompanies = useMemo(
    () => rankCompaniesByComposite(filteredCompanies),
    [filteredCompanies],
  );

  const activeMetricRankedCompanies = useMemo(
    () => rankCompaniesByMetric(filteredCompanies, rankingMetric),
    [filteredCompanies, rankingMetric],
  );

  const displayedCompanies = useMemo(
    () => orderForDisplay(activeMetricRankedCompanies, rankingMetric, displayDirection),
    [activeMetricRankedCompanies, displayDirection, rankingMetric],
  );

  const handleRankingMetric = (metric: RankingMetric) => {
    if (rankingMetric === metric) {
      setDisplayDirection((current) => current === 'best-first' ? 'worst-first' : 'best-first');
    } else {
      setRankingMetric(metric);
      setDisplayDirection('best-first');
    }
  };

  const metricDirectionLabel = displayDirection === 'best-first' ? '높은 순' : '낮은 순';
  const activeRankingLabel = `${RANKING_METRICS[rankingMetric].label} 순위`;
  const averageCagr = state.status === 'ready' ? state.data.spotlight.averageCagr : 0;
  const averageMargin = state.status === 'ready' ? state.data.spotlight.averageMargin : 0;
  const averageDebtRatio = state.status === 'ready'
    ? state.data.spotlight.averageLiabilitiesToAssets
    : 0;
  const officialRankByCompanyId = new Map(
    officialRankedCompanies.map(({ company, rank }) => [company.companyId, rank]),
  );
  const selectedCompanies = Array.from(selectedCompanyIds)
    .map((companyId) => filteredCompanies.find((company) => company.companyId === companyId))
    .filter((company): company is ComparisonCompany => Boolean(company));
  const focusedCompany = filteredCompanies.find((company) => company.companyId === focusedCompanyId);
  const analysisCompany = selectedCompanies.length === 1
    ? selectedCompanies[0]
    : focusedCompany ?? officialRankedCompanies[0]?.company;
  const comparisonCompanies = selectedCompanies.length === 2 ? selectedCompanies : [];
  const analysisPeriods = analysisCompany ? historicalPeriods(analysisCompany) : [];
  const analysisForecastPeriods = analysisCompany ? forecastPeriods(analysisCompany) : [];
  const comparisonPeriods = comparisonCompanies.map(historicalPeriods);
  const analysisReasons = analysisCompany ? rankReason(analysisCompany, filteredCompanies) : [];
  const benchmarkScatterData: readonly BenchmarkScatterPoint[] = filteredCompanies.map((company) => ({
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
  }));

  if (state.status === 'loading') {
    return (
      <main className="financial-league-page league-loading" aria-live="polite">
        <RefreshCw size={24} className="spin" />
        <strong>기업 비교 스냅샷을 불러오고 있습니다...</strong>
      </main>
    );
  }

  if (state.status === 'error') {
    return (
      <main className="financial-league-page league-loading" role="alert">
        <AlertCircle size={28} color="#dc2626" />
        <strong>데이터 로드 실패</strong>
        <p>{state.message}</p>
        <Button variant="primary" type="button" onClick={() => setReloadKey((k) => k + 1)}>
          스냅샷 생성
        </Button>
      </main>
    );
  }

  return (
    <main className="financial-league-page" aria-label="기업 랭킹 리그 화면">
      <header className="league-page-heading">
        <div>
          <span className="league-page-eyebrow">COMPANY COMPARISON</span>
          <div className="league-page-title-row">
            <h1>기업 비교</h1>
            <span>{filteredCompanies.length}개 기업</span>
          </div>
          <p>{state.data.historicalStartYear}~{state.data.historicalEndYear} 관측 재무 성과와 명시된 예측 가정을 기준으로 성장성·수익성·안정성을 비교합니다.</p>
        </div>
        <Button type="button" onClick={() => setReloadKey((key) => key + 1)}>
          <RefreshCw size={14} /> 스냅샷 새로고침
        </Button>
      </header>

      {state.data.snapshot.status === 'partial' && (
        <section className="comparison-state-card comparison-state-card--error" role="status">
          <AlertCircle size={20} />
          <div><strong>일부 기업이 비교에서 제외되었습니다.</strong><p>{state.data.exclusions.map((item) => item.displayName).join(', ')}</p></div>
        </section>
      )}

      {/* =========================================================================
          1. Top Control Bar: Ranking Controls | Live Sorting
         ========================================================================= */}
      <section className="league-top-filter-bar" aria-label="순위 정렬 제어">
        {/* Left: Quick ranking metric controls */}
        <div className="filter-section-block">
          <span className="filter-section-label">빠른 표시 정렬</span>
          <div className="filter-pills-row">
            {(['Overall', 'Revenue', 'Profit', 'Growth'] as const).map((factor) => {
              const factorMetric: Record<typeof factor, RankingMetric> = {
                Overall: 'composite', Revenue: 'revenue', Profit: 'operatingIncome', Growth: 'revenueCagr',
              };
              const isActive = rankingMetric === factorMetric[factor];
              return (
                <button
                  type="button"
                  key={factor}
                  className={`dropdown-filter-pill ${isActive ? 'is-active' : ''}`}
                  onClick={() => handleRankingMetric(factorMetric[factor])}
                  aria-pressed={isActive}
                >
                  <span>{FACTOR_LABELS[factor]}</span>
                  <ChevronDown size={11} />
                </button>
              );
            })}
          </div>
        </div>

        {/* Right: Live sorting pills */}
        <div className="filter-section-block">
          <span className="filter-section-label">실시간 정렬 기준</span>
          <div className="filter-pills-row">
            <div className="sort-status-pill">
              <ArrowUpDown size={11} />
              <span>
                {activeRankingLabel} · {metricDirectionLabel}
              </span>
              <button
                type="button"
                className="sort-clear-btn"
                onClick={() => {
                  setRankingMetric('composite');
                  setDisplayDirection('best-first');
                }}
                aria-label="정렬 초기화"
                title="정렬 초기화"
              >
                <X size={10} />
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* =========================================================================
          2. Main Layout: Left Table (70%) vs Right Spotlight Cards & Metrics (30%)
         ========================================================================= */}
      <div className="league-main-grid">
        {/* Left Column: League Ranking Table */}
        <div className="league-table-card">
          <div className="league-table-scroll-wrap">
            <table className="league-pixel-table">
              <thead>
                <tr>
                  <th className="col-th-rank">{activeRankingLabel}</th>
                  <th className="col-th-select">비교</th>
                  <th className="col-th-company">기업명</th>
                  {([
                    ['revenue', '매출액'],
                    ['operatingIncome', '영업이익'],
                    ['revenueCagr', '관측 구간 매출 성장률'],
                    ['operatingMargin', '영업이익률'],
                  ] as const).map(([metric, label]) => (
                    <th
                      key={metric}
                      className={`metric-rank-header col-th-${metric} ${rankingMetric === metric ? 'is-active' : ''}`}
                      aria-sort={rankingMetric === metric
                        ? (displayDirection === 'best-first' ? 'descending' : 'ascending')
                        : 'none'}
                    >
                      <button type="button" onClick={() => handleRankingMetric(metric)}>
                        {label}<span aria-hidden="true">{rankingMetric === metric
                          ? (displayDirection === 'best-first' ? '▼' : '▲')
                          : '↕'}</span>
                      </button>
                    </th>
                  ))}
                  <th className="col-th-debtRatio">부채비율</th>
                  <th
                    className={`metric-rank-header col-th-composite ${rankingMetric === 'composite' ? 'is-active' : ''}`}
                    aria-sort={rankingMetric === 'composite'
                      ? (displayDirection === 'best-first' ? 'descending' : 'ascending')
                      : 'none'}
                  >
                    <button type="button" onClick={() => handleRankingMetric('composite')}>
                      종합점수<span aria-hidden="true">{rankingMetric === 'composite'
                        ? (displayDirection === 'best-first' ? '▼' : '▲')
                        : '↕'}</span>
                    </button>
                  </th>
                </tr>
              </thead>
              <tbody>
                {displayedCompanies.map(({ company, rank }) => {
                  const isFocused = company.companyId === focusedCompanyId;
                  const isSelected = selectedCompanyIds.has(company.companyId);
                  const latest = latestHistoricalPeriod(company);

                  return (
                    <tr
                      key={company.companyId}
                      className={`league-table-row ${isFocused ? 'is-selected' : ''}`}
                      onClick={() => setFocusedCompanyId(company.companyId)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault();
                          setFocusedCompanyId(company.companyId);
                        }
                      }}
                      tabIndex={0}
                      aria-selected={isFocused}
                    >
                      {/* 1. Rank */}
                      <td className="col-th-rank">
                        <div className="rank-cell-display">
                          <span>{rank}</span>
                        </div>
                      </td>

                      <td className="col-th-select">
                        <input
                          type="checkbox"
                          checked={isSelected}
                          aria-label={`${company.displayName} 비교 선택`}
                          onClick={(event) => event.stopPropagation()}
                          onChange={() => {
                            if (!isSelected) setFocusedCompanyId(company.companyId);
                            setSelectedCompanyIds((current) =>
                              toggleCompanySelection(current, company.companyId));
                          }}
                        />
                      </td>

                      {/* 2. Company Logo + Name */}
                      <td className="col-th-company">
                        <div className="company-cell-flex">
                          <CompanyLogoBadge
                            companyId={company.companyId}
                            companyName={company.displayName}
                            size={22}
                          />
                          <AppLink
                            to={`/dashboard?companyId=${encodeURIComponent(company.companyId)}`}
                            className="company-name-text"
                            onClick={(e) => {
                              e.stopPropagation();
                            }}
                            title={`${company.displayName} BI 대시보드 바로가기`}
                          >
                            {company.displayName}
                          </AppLink>
                        </div>
                      </td>

                      <td className={`col-th-revenue ${rankingMetric === 'revenue' ? 'is-ranked' : ''}`}>
                        <strong>{latest ? formatAmount(latest.revenue, company) : '—'}</strong>
                      </td>
                      <td className={`col-th-operatingIncome ${rankingMetric === 'operatingIncome' ? 'is-ranked' : ''}`}>
                        <strong>{latest ? formatAmount(latest.operatingIncome, company) : '—'}</strong>
                      </td>
                      <td className={`col-th-revenueCagr ${rankingMetric === 'revenueCagr' ? 'is-ranked' : ''}`}>
                        <strong
                          className={`growth-rate ${company.revenueCagr > 0
                            ? 'is-positive'
                            : company.revenueCagr < 0
                              ? 'is-negative'
                              : 'is-neutral'}`}
                          aria-label={`관측 구간 매출 성장률 ${company.revenueCagr.toFixed(1)}%, ${company.revenueCagr > 0
                            ? '상승'
                            : company.revenueCagr < 0
                              ? '하락'
                              : '변동 없음'}`}
                        >
                          <span className="growth-rate-arrow" aria-hidden="true">
                            {company.revenueCagr > 0 ? '▲' : company.revenueCagr < 0 ? '▼' : '—'}
                          </span>
                          <span>{company.revenueCagr.toFixed(1)}%</span>
                        </strong>
                      </td>
                      <td className={`col-th-operatingMargin ${rankingMetric === 'operatingMargin' ? 'is-ranked' : ''}`}>
                        <strong className={company.operatingMargin < 0 ? 'metric-negative' : ''}>
                          {company.operatingMargin.toFixed(1)}%
                        </strong>
                      </td>
                      <td className="col-th-debtRatio">
                        <strong title={`순부채/매출 ${company.netDebtToRevenue.toFixed(1)}%`}>
                          {company.liabilitiesToAssets.toFixed(1)}%
                        </strong>
                      </td>
                      <td className={`col-th-composite ${rankingMetric === 'composite' ? 'is-ranked' : ''}`}>
                        <div className="debt-grade-cell" title="성장성 35% + 수익성 35% + 안정성 30%">
                          <span className={`tier-round-pill pill-${company.tier.toLowerCase()}`}>
                            {company.tier}
                          </span>
                          <strong>{company.compositeScore.toFixed(1)}</strong>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Right Column: selection-driven company analysis */}
        <div className="league-side-column">
          <section className="company-analysis-panel" aria-label="선택 기업 분석">
            <div className="analysis-panel-heading">
              <div>
                <span>{comparisonCompanies.length === 2 ? 'COMPARE MODE' : 'COMPANY INSIGHT'}</span>
                <strong>{comparisonCompanies.length === 2 ? '선택 기업 비교' : '선택 기업 분석'}</strong>
              </div>
              <small>{comparisonCompanies.length === 2 ? '체크한 2개 기업' : '행을 클릭하거나 비교 체크'}</small>
            </div>

            {comparisonCompanies.length === 2 ? (
              <>
                <div className="analysis-company-pair">
                  {comparisonCompanies.map((company, index) => (
                    <div key={company.companyId} className={`analysis-company-identity is-${index === 0 ? 'a' : 'b'}`}>
                      <span className="analysis-compare-key">{index === 0 ? 'A' : 'B'}</span>
                      <CompanyLogoBadge companyId={company.companyId} companyName={company.displayName} size={25} />
                      <div>
                        <strong title={company.displayName}>{company.displayName}</strong>
                        <span>종합 {officialRankByCompanyId.get(company.companyId)}위 · {company.tier}등급 · {company.compositeScore.toFixed(1)}점</span>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="analysis-section-block">
                  <div className="analysis-section-title">
                    <strong>핵심 지표 우위</strong>
                    <span>부채비율은 낮을수록 양호</span>
                  </div>
                  <div className="comparison-metric-grid">
                    {[
                      { label: '종합점수', a: comparisonCompanies[0].compositeScore, b: comparisonCompanies[1].compositeScore, suffix: '점', lower: false },
                      { label: '매출 성장률', a: comparisonCompanies[0].revenueCagr, b: comparisonCompanies[1].revenueCagr, suffix: '%', lower: false },
                      { label: '영업이익률', a: comparisonCompanies[0].operatingMargin, b: comparisonCompanies[1].operatingMargin, suffix: '%', lower: false },
                      { label: '부채비율', a: comparisonCompanies[0].liabilitiesToAssets, b: comparisonCompanies[1].liabilitiesToAssets, suffix: '%', lower: true },
                    ].map((metric) => {
                      const aWins = metric.lower ? metric.a < metric.b : metric.a > metric.b;
                      const bWins = metric.lower ? metric.b < metric.a : metric.b > metric.a;
                      return (
                        <div className="comparison-metric-row" key={metric.label}>
                          <strong className={aWins ? 'is-winner-a' : ''}>{metric.a.toFixed(1)}{metric.suffix}</strong>
                          <span>{metric.label}</span>
                          <strong className={bWins ? 'is-winner-b' : ''}>{metric.b.toFixed(1)}{metric.suffix}</strong>
                        </div>
                      );
                    })}
                  </div>
                </div>

                <div className="analysis-section-block">
                  <div className="analysis-section-title">
                    <strong>평가축별 우위</strong>
                    <span>종합점수 계산 기준</span>
                  </div>
                  <div className="comparison-score-list">
                    {SCORE_DIMENSIONS.map((dimension) => {
                      const aScore = comparisonCompanies[0][dimension.key];
                      const bScore = comparisonCompanies[1][dimension.key];
                      return (
                        <div className="comparison-score-row" key={dimension.key}>
                          <span>{dimension.label} <small>{Math.round(dimension.weight * 100)}%</small></span>
                          <div className="comparison-score-values">
                            <strong className={aScore > bScore ? 'is-winner-a' : ''}>A {aScore.toFixed(1)}</strong>
                            <i aria-hidden="true"><b style={{ width: `${aScore}%` }} /><b style={{ width: `${bScore}%` }} /></i>
                            <strong className={bScore > aScore ? 'is-winner-b' : ''}>B {bScore.toFixed(1)}</strong>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                <div className="analysis-section-block trend-section">
                  <div className="analysis-section-title">
                    <strong>공통 관측 기간 매출 추이</strong>
                    <span>{comparisonPeriods[0]?.[0]?.year ?? '기준연도'}년=100 지수</span>
                  </div>
                  <div className="comparison-trend-legend">
                    <span><i className="is-a" />A {comparisonCompanies[0].displayName}</span>
                    <span><i className="is-b" />B {comparisonCompanies[1].displayName}</span>
                  </div>
                  <ComparisonTrendChart
                    first={indexedSeries(comparisonPeriods[0])}
                    second={indexedSeries(comparisonPeriods[1])}
                  />
                </div>
              </>
            ) : analysisCompany ? (
              <>
                <div className="analysis-company-summary">
                  <div className="analysis-company-identity">
                    <CompanyLogoBadge companyId={analysisCompany.companyId} companyName={analysisCompany.displayName} size={30} />
                    <div>
                      <strong title={analysisCompany.displayName}>{analysisCompany.displayName}</strong>
                      <span>{filteredCompanies.length}개 기업 중 종합 {officialRankByCompanyId.get(analysisCompany.companyId)}위</span>
                    </div>
                  </div>
                  <div className="analysis-total-score">
                    <span className={`tier-round-pill pill-${analysisCompany.tier.toLowerCase()}`}>{analysisCompany.tier}</span>
                    <strong>{analysisCompany.compositeScore.toFixed(1)}</strong>
                    <small>종합점수</small>
                  </div>
                </div>

                <div className="analysis-section-block rank-reason-section">
                  <div className="analysis-section-title">
                    <strong>왜 이 순위인가?</strong>
                    <span>성장 35 · 수익 35 · 안정 30</span>
                  </div>
                  <div className="score-contribution-list">
                    {SCORE_DIMENSIONS.map((dimension) => {
                      const score = analysisCompany[dimension.key];
                      return (
                        <div className="score-contribution-row" key={dimension.key}>
                          <span>{dimension.label}<small>{scoreRank(filteredCompanies, analysisCompany, dimension)}위</small></span>
                          <i><b style={{ width: `${score}%` }} /></i>
                          <strong>{score.toFixed(1)}</strong>
                          <small>+{(score * dimension.weight).toFixed(1)}</small>
                        </div>
                      );
                    })}
                  </div>
                  <div className="rank-reason-copy">
                    {analysisReasons.map((reason) => <p key={reason}>{reason}</p>)}
                  </div>
                </div>

                <div className="analysis-section-block">
                  <div className="analysis-section-title">
                    <strong>{filteredCompanies.length}개 기업 평균 대비</strong>
                    <span>현재 기업 / 전체 평균 / 차이</span>
                  </div>
                  <div className="benchmark-compare-list">
                    {[
                      { label: '매출 성장률', value: analysisCompany.revenueCagr, average: averageCagr, lower: false },
                      { label: '영업이익률', value: analysisCompany.operatingMargin, average: averageMargin, lower: false },
                      { label: '부채비율', value: analysisCompany.liabilitiesToAssets, average: averageDebtRatio, lower: true },
                    ].map((metric) => {
                      const delta = metric.value - metric.average;
                      const favorable = metric.lower ? delta < 0 : delta > 0;
                      return (
                        <div className="benchmark-compare-row" key={metric.label}>
                          <span>{metric.label}</span>
                          <strong>{metric.value.toFixed(1)}%</strong>
                          <small>평균 {metric.average.toFixed(1)}%</small>
                          <b className={delta === 0 ? 'is-neutral' : favorable ? 'is-favorable' : 'is-unfavorable'}>
                            {metric.lower && delta < 0 ? `${Math.abs(delta).toFixed(1)}%p 낮음` : signedPoint(delta)}
                          </b>
                        </div>
                      );
                    })}
                  </div>
                </div>

                <div className="analysis-section-block trend-section">
                  <div className="analysis-section-title">
                    <strong>{analysisCompany.historicalStartYear}~{analysisCompany.historicalEndYear} 핵심 추이</strong>
                    <span>실적 방향성</span>
                  </div>
                  {[
                    { label: '매출', points: analysisPeriods.map((period) => ({ year: period.year, value: period.revenue })), color: '#107c41', gradientId: 'revenue-trend-fill' },
                    { label: '영업이익', points: analysisPeriods.map((period) => ({ year: period.year, value: period.operatingIncome })), color: '#2563eb', gradientId: 'profit-trend-fill' },
                  ].map((metric) => {
                    const change = percentChange(metric.points.map((point) => point.value));
                    return (
                      <div className="single-trend-row" key={metric.label}>
                        <div>
                          <span>{metric.label}</span>
                          <strong>{formatAmount(metric.points[metric.points.length - 1]?.value ?? 0, analysisCompany)}</strong>
                          <small className={change !== null && change < 0 ? 'is-down' : ''}>{change === null ? '—' : `${change >= 0 ? '+' : ''}${change.toFixed(1)}%`}</small>
                        </div>
                        <FinancialTrendChart
                          points={metric.points}
                          color={metric.color}
                          gradientId={metric.gradientId}
                          label={metric.label}
                          valueFormatter={(value) => formatAmount(value, analysisCompany)}
                        />
                      </div>
                    );
                  })}
                </div>

                {analysisForecastPeriods.length > 0 && (
                  <div className="analysis-section-block trend-section">
                    <div className="analysis-section-title">
                      <strong>{analysisForecastPeriods[0].year}~{analysisForecastPeriods[analysisForecastPeriods.length - 1].year} 가정 기반 전망</strong>
                      <span>순위 점수에는 미반영</span>
                    </div>
                    <div className="single-trend-row">
                      <div>
                        <span>예상 매출</span>
                        <strong>{formatAmount(analysisForecastPeriods[analysisForecastPeriods.length - 1].revenue, analysisCompany)}</strong>
                        <small>FORECAST</small>
                      </div>
                      <FinancialTrendChart
                        points={[
                          ...(analysisPeriods.length > 0
                            ? [{
                                year: analysisPeriods[analysisPeriods.length - 1].year,
                                value: analysisPeriods[analysisPeriods.length - 1].revenue,
                              }]
                            : []),
                          ...analysisForecastPeriods.map((period) => ({
                            year: period.year,
                            value: period.revenue,
                          })),
                        ]}
                        color="#7c3aed"
                        gradientId="forecast-revenue-fill"
                        label="가정 기반 예상 매출"
                        valueFormatter={(value) => formatAmount(value, analysisCompany)}
                      />
                    </div>
                    <p className="comparison-forecast-note">
                      {state.data.assumptions.find(
                        (item) => item.assumptionId === analysisForecastPeriods[0].assumptionId,
                      )?.description}
                    </p>
                  </div>
                )}
              </>
            ) : null}
          </section>

          <section className="interactive-distribution-panel position-analysis-panel" aria-label="기업군 내 성장성과 수익성 위치">
            <div className="distribution-title-row">
              <div>
                <span className="distribution-main-title">성장성 × 수익성 포지션</span>
                <p className="distribution-description">선택 기업이 전체 {filteredCompanies.length}개 기업에서 어디에 위치하는지 확인하세요.</p>
              </div>
              <span className="distribution-scope">{filteredCompanies.length}개 기업</span>
            </div>
            <div className="distribution-sub-widget benchmark-scatter-widget is-standalone">
              <div className="benchmark-scatter-title-row">
                <span className="dist-widget-heading">평균 기준선: 성장률 {averageCagr.toFixed(1)}% · 이익률 {averageMargin.toFixed(1)}%</span>
                <div className="benchmark-scatter-legend" aria-label="산점도 범례">
                  {comparisonCompanies.length === 2 ? (
                    <><span><i className="is-compare-a" />기업 A</span><span><i className="is-compare-b" />기업 B</span></>
                  ) : <span><i className="is-selected" />선택 기업</span>}
                  <span><i />기타</span>
                </div>
              </div>
              <div
                className="benchmark-scatter-chart"
                role="img"
                aria-label="기업별 매출 성장률과 영업이익률 산점도. 점을 선택하면 표에서 기업이 강조됩니다."
              >
                <span className="quadrant-label is-top-left">안정 수익형</span>
                <span className="quadrant-label is-top-right">고성장·고수익</span>
                <span className="quadrant-label is-bottom-left">관찰 필요</span>
                <span className="quadrant-label is-bottom-right">성장 투자형</span>
                <ResponsiveContainer width="100%" height="100%">
                  <ScatterChart margin={{ top: 22, right: 16, bottom: 6, left: -4 }}>
                    <CartesianGrid stroke="#e5ece8" strokeDasharray="3 3" />
                    <XAxis
                      type="number"
                      dataKey="growth"
                      name="매출 성장률"
                      unit="%"
                      tick={{ fill: '#64746b', fontSize: 9 }}
                      tickLine={false}
                      axisLine={{ stroke: '#cbd8d1' }}
                      tickCount={5}
                      domain={['auto', 'auto']}
                    />
                    <YAxis
                      type="number"
                      dataKey="margin"
                      name="영업이익률"
                      unit="%"
                      width={42}
                      tick={{ fill: '#64746b', fontSize: 9 }}
                      tickLine={false}
                      axisLine={{ stroke: '#cbd8d1' }}
                      tickCount={5}
                      domain={['auto', 'auto']}
                    />
                    <ReferenceLine x={averageCagr} stroke="#2563eb" strokeDasharray="4 3" />
                    <ReferenceLine y={averageMargin} stroke="#107c41" strokeDasharray="4 3" />
                    <Tooltip cursor={{ stroke: '#94a3b8', strokeDasharray: '3 3' }} content={<BenchmarkScatterTooltip />} />
                    <Scatter
                      data={benchmarkScatterData}
                      shape={renderBenchmarkScatterMarker}
                      onClick={(point) => {
                        const companyId = (point as { payload?: BenchmarkScatterPoint }).payload?.companyId;
                        if (companyId) setFocusedCompanyId(companyId);
                      }}
                    />
                  </ScatterChart>
                </ResponsiveContainer>
              </div>
              <div className="benchmark-scatter-axis-labels" aria-hidden="true">
                <span>낮은 성장</span>
                <strong>매출 성장률</strong>
                <span>높은 성장</span>
              </div>
            </div>
          </section>
        </div>
      </div>

      {/* =========================================================================
          3. Bottom Status Footer Bar
         ========================================================================= */}
      <footer className="league-bottom-status-bar" aria-label="데이터 상태">
        <div className="footer-left-links">
          <span className="footer-link-item">
            <Database size={11} /> 데이터 출처: 검증된 BI 스냅샷 {state.data.snapshot.sourceSnapshotIds.length}개 · 원본 셀 근거 {state.data.evidence.length}건
          </span>
          <span className="footer-link-item">
            <RefreshCw size={11} /> 현재 순위: {RANKING_METRICS[rankingMetric].label} 기준 · {metricDirectionLabel}
          </span>
        </div>
        <div className="footer-right-time">
          <span className="footer-link-item">
            <Clock size={11} /> 최종 업데이트: {new Date(state.data.snapshot.generatedAt).toLocaleString('ko-KR')}
          </span>
        </div>
      </footer>
    </main>
  );
}
