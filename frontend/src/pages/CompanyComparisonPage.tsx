import {
  AlertCircle,
  Clock,
  Database,
  RefreshCw,
} from 'lucide-react';
import { useMemo, useState } from 'react';
import { Button } from '../shared/ui';
import { CompanyLogoBadge } from '../features/company-comparison/CompanyLogoBadge';
import {
  CompanyRankingTable,
  ComparisonRankingToolbar,
} from '../features/company-comparison/ComparisonRanking';
import {
  ComparisonTrendChart,
  FinancialTrendChart,
  type BenchmarkScatterPoint,
} from '../features/company-comparison/CompanyComparisonCharts';
import { ComparisonPositionPanel } from '../features/company-comparison/ComparisonPositionPanel';
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
      <section className="financial-league-page league-loading" aria-live="polite">
        <RefreshCw size={24} className="spin" />
        <strong>기업 비교 스냅샷을 불러오고 있습니다...</strong>
      </section>
    );
  }

  if (state.status === 'error') {
    return (
      <section className="financial-league-page league-loading" role="alert">
        <AlertCircle size={28} color="#dc2626" />
        <strong>데이터 로드 실패</strong>
        <p>{state.message}</p>
        <Button variant="primary" type="button" onClick={() => setReloadKey((k) => k + 1)}>
          스냅샷 생성
        </Button>
      </section>
    );
  }

  return (
    <section className="financial-league-page" aria-label="기업 랭킹 리그 화면">
      <h1 className="page-visually-hidden">기업 비교</h1>

      {state.data.snapshot.status === 'partial' && (
        <section className="comparison-state-card comparison-state-card--error" role="status">
          <AlertCircle size={20} />
          <div><strong>일부 기업이 비교에서 제외되었습니다.</strong><p>{state.data.exclusions.map((item) => item.displayName).join(', ')}</p></div>
        </section>
      )}

      <ComparisonRankingToolbar
        rankingMetric={rankingMetric}
        activeRankingLabel={activeRankingLabel}
        metricDirectionLabel={metricDirectionLabel}
        onMetricChange={handleRankingMetric}
        onReset={() => {
          setRankingMetric('composite');
          setDisplayDirection('best-first');
        }}
        onRefresh={() => setReloadKey((key) => key + 1)}
      />

      {/* =========================================================================
          2. Main Layout: Left Table (70%) vs Right Spotlight Cards & Metrics (30%)
         ========================================================================= */}
      <div className="league-main-grid">
        <CompanyRankingTable
          companies={displayedCompanies}
          rankingMetric={rankingMetric}
          displayDirection={displayDirection}
          activeRankingLabel={activeRankingLabel}
          focusedCompanyId={focusedCompanyId}
          selectedCompanyIds={selectedCompanyIds}
          onMetricChange={handleRankingMetric}
          onFocusCompany={setFocusedCompanyId}
          onToggleCompany={(companyId) => {
            if (!selectedCompanyIds.has(companyId)) setFocusedCompanyId(companyId);
            setSelectedCompanyIds((current) => toggleCompanySelection(current, companyId));
          }}
        />

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

          <ComparisonPositionPanel
            companiesCount={filteredCompanies.length}
            averageCagr={averageCagr}
            averageMargin={averageMargin}
            comparisonMode={comparisonCompanies.length === 2}
            points={benchmarkScatterData}
            onSelectCompany={setFocusedCompanyId}
          />
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
    </section>
  );
}
