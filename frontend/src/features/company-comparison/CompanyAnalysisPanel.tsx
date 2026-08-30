import { CompanyLogoBadge } from './CompanyLogoBadge';
import { ComparisonTrendChart, FinancialTrendChart } from './CompanyComparisonCharts';
import {
  formatAmount,
  indexedSeries,
  percentChange,
  SCORE_DIMENSIONS,
  scoreRank,
  signedPoint,
} from './analysis';
import type { CompanyComparisonController } from './useCompanyComparisonController';
import type { CompanyComparisonSnapshot } from './types';
import './CompanyAnalysisPanel.css';

type AnalysisController = Pick<
  CompanyComparisonController,
  | 'companies'
  | 'officialRankByCompanyId'
  | 'analysisCompany'
  | 'comparisonCompanies'
  | 'analysisPeriods'
  | 'analysisForecastPeriods'
  | 'comparisonPeriods'
  | 'analysisReasons'
  | 'averageCagr'
  | 'averageMargin'
  | 'averageDebtRatio'
>;

interface CompanyAnalysisPanelProps {
  readonly comparison: AnalysisController;
  readonly assumptions: CompanyComparisonSnapshot['assumptions'];
}

/** Selection-driven analysis panel for either one focused company or a two-company comparison. */
export function CompanyAnalysisPanel({ comparison, assumptions }: CompanyAnalysisPanelProps) {
  const {
    companies,
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
  } = comparison;

  return (
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
                <span>{companies.length}개 기업 중 종합 {officialRankByCompanyId.get(analysisCompany.companyId)}위</span>
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
                    <span>{dimension.label}<small>{scoreRank(companies, analysisCompany, dimension)}위</small></span>
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
              <strong>{companies.length}개 기업 평균 대비</strong>
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
                {assumptions.find(
                  (item) => item.assumptionId === analysisForecastPeriods[0].assumptionId,
                )?.description}
              </p>
            </div>
          )}
        </>
      ) : null}
    </section>
  );
}
