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
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { AppLink } from '../app/router';
import { CompanyLogoBadge } from '../features/company-comparison-v2/CompanyLogoBadge';
import {
  RANKING_METRICS,
  latestHistoricalCandle,
  orderForDisplay,
  rankCompaniesByComposite,
  rankCompaniesByMetric,
  toggleCompanySelection,
  type DisplayDirection,
  type RankingMetric,
} from '../features/company-comparison-v2/metricRanking';
import { useFinancialLeague } from '../features/company-comparison-v2/useFinancialLeague';
import type { LeagueCompany } from '../features/company-comparison-v2/leagueTypes';
import '../features/company-comparison-v2/financial-league.css';

const FACTOR_LABELS: Record<'Overall' | 'Revenue' | 'Profit' | 'Growth', string> = {
  Overall: '종합순위',
  Revenue: '매출액',
  Profit: '영업이익',
  Growth: '성장률',
};

interface BenchmarkScatterPoint {
  readonly companyId: string;
  readonly companyName: string;
  readonly growth: number;
  readonly margin: number;
  readonly tone: 'selected' | 'compare-a' | 'compare-b' | 'default';
}

const SCORE_DIMENSIONS = [
  { key: 'growthScore', label: '성장성', weight: 0.35 },
  { key: 'profitabilityScore', label: '수익성', weight: 0.35 },
  { key: 'stabilityScore', label: '안정성', weight: 0.30 },
] as const;

type ScoreDimension = (typeof SCORE_DIMENSIONS)[number];

function BenchmarkScatterTooltip({
  active,
  payload,
}: {
  readonly active?: boolean;
  readonly payload?: readonly { readonly payload: BenchmarkScatterPoint }[];
}) {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  return (
    <div className="benchmark-scatter-tooltip">
      <strong>{point.companyName}</strong>
      <span>매출 성장률 <b>{point.growth.toFixed(1)}%</b></span>
      <span>영업이익률 <b>{point.margin.toFixed(1)}%</b></span>
    </div>
  );
}

function formatAmount(value: number, company: LeagueCompany): string {
  const currency = company.currency === 'USD' ? '$' : company.currency === 'KRW' ? '₩' : `${company.currency} `;
  const suffix = company.scale === 'millions' ? 'M' : company.scale === 'billions' ? 'B' : company.scale === 'thousands' ? 'K' : '';
  const sign = value < 0 ? '-' : '';
  return `${sign}${currency}${Math.round(Math.abs(value)).toLocaleString()}${suffix}`;
}

function historicalCandles(company: LeagueCompany) {
  return [...company.candles]
    .filter((candle) => candle.periodType === 'historical')
    .sort((left, right) => left.year - right.year);
}

function scoreRank(
  companies: readonly LeagueCompany[],
  company: LeagueCompany,
  dimension: ScoreDimension,
): number {
  return companies.filter((candidate) => candidate[dimension.key] > company[dimension.key]).length + 1;
}

function rankReason(company: LeagueCompany, companies: readonly LeagueCompany[]): readonly string[] {
  const dimensions = SCORE_DIMENSIONS.map((dimension) => ({
    ...dimension,
    score: company[dimension.key],
    rank: scoreRank(companies, company, dimension),
    contribution: company[dimension.key] * dimension.weight,
  })).sort((left, right) => right.contribution - left.contribution);
  const strongest = dimensions[0];
  const weakest = [...dimensions].sort((left, right) => left.score - right.score)[0];
  const spread = strongest.score - weakest.score;

  const first = `${strongest.label} ${strongest.score.toFixed(1)}점(기업군 ${strongest.rank}위)이 가중 점수 ${strongest.contribution.toFixed(1)}점으로 가장 크게 기여했습니다.`;
  const second = spread < 8
    ? '세 평가축의 점수 차이가 작아 특정 지표에 치우치지 않은 균형형 평가입니다.'
    : `${weakest.label} ${weakest.score.toFixed(1)}점은 세 평가축 중 가장 낮아 종합순위의 주요 감점 요인입니다.`;
  return [first, second];
}

function signedPoint(value: number): string {
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}%p`;
}

function percentChange(values: readonly number[]): number | null {
  if (values.length < 2 || values[0] === 0) return null;
  return ((values[values.length - 1] - values[0]) / Math.abs(values[0])) * 100;
}

function indexedSeries(values: readonly number[]): readonly number[] {
  if (!values.length || values[0] === 0) return values.map(() => 100);
  return values.map((value) => (value / values[0]) * 100);
}

function FinancialTrendChart({
  values,
  color,
  gradientId,
  label,
  valueFormatter,
}: {
  readonly values: readonly number[];
  readonly color: string;
  readonly gradientId: string;
  readonly label: string;
  readonly valueFormatter: (value: number) => string;
}) {
  const data = values.map((value, index) => ({ year: 2021 + index, value }));

  return (
    <div className="analysis-trend-chart" role="img" aria-label={`2021년부터 2025년까지 ${label} 추이`}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 7, right: 5, bottom: 0, left: 5 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.22} />
              <stop offset="100%" stopColor={color} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} stroke="#e8efeb" strokeDasharray="2 3" />
          <XAxis dataKey="year" tick={{ fill: '#84928b', fontSize: 7.5 }} tickLine={false} axisLine={false} interval={0} />
          <YAxis hide domain={['dataMin', 'dataMax']} />
          <Tooltip
            formatter={(value) => [valueFormatter(Number(value)), label]}
            labelFormatter={(year) => `${year}년`}
            contentStyle={{ border: '1px solid #d7e4dd', borderRadius: 7, padding: '6px 8px', fontSize: 9 }}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={2.2}
            fill={`url(#${gradientId})`}
            dot={{ r: 2.5, fill: '#ffffff', stroke: color, strokeWidth: 1.5 }}
            activeDot={{ r: 4, fill: color, stroke: '#ffffff', strokeWidth: 1.5 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function ComparisonTrendChart({
  first,
  second,
}: {
  readonly first: readonly number[];
  readonly second: readonly number[];
}) {
  const data = first.map((value, index) => ({ year: 2021 + index, a: value, b: second[index] }));
  return (
    <div className="analysis-trend-chart is-comparison" role="img" aria-label="두 기업의 2021년부터 2025년까지 매출 성장 지수 비교">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 7, right: 5, bottom: 0, left: 5 }}>
          <CartesianGrid vertical={false} stroke="#e8efeb" strokeDasharray="2 3" />
          <XAxis dataKey="year" tick={{ fill: '#84928b', fontSize: 7.5 }} tickLine={false} axisLine={false} interval={0} />
          <YAxis hide domain={['dataMin', 'dataMax']} />
          <Tooltip
            formatter={(value, name) => [`${Number(value).toFixed(1)}`, name === 'a' ? '기업 A' : '기업 B']}
            labelFormatter={(year) => `${year}년 · 2021=100`}
            contentStyle={{ border: '1px solid #d7e4dd', borderRadius: 7, padding: '6px 8px', fontSize: 9 }}
          />
          <Line type="monotone" dataKey="a" stroke="#107c41" strokeWidth={2.2} dot={{ r: 2.5, fill: '#fff', strokeWidth: 1.5 }} activeDot={{ r: 4 }} />
          <Line type="monotone" dataKey="b" stroke="#2563eb" strokeWidth={2.2} dot={{ r: 2.5, fill: '#fff', strokeWidth: 1.5 }} activeDot={{ r: 4 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

interface BenchmarkScatterMarkerProps {
  readonly cx?: number;
  readonly cy?: number;
  readonly payload?: BenchmarkScatterPoint;
}

function BenchmarkScatterMarker({ cx = 0, cy = 0, payload }: BenchmarkScatterMarkerProps) {
  if (!payload || payload.tone === 'default') {
    return <circle cx={cx} cy={cy} r={4} fill="#94a3b8" fillOpacity={0.35} stroke="#ffffff" strokeWidth={1} />;
  }
  const borderColor = payload.tone === 'compare-a' ? '#107c41' : '#2563eb';
  const baseName = payload.companyName
    .split(' (')[0]
    .replace(/\s+(Inc\.?|Co\.?|Systems|Labs|Networks|Tech|Digital|AI|Materials|Dynamics|Logic)$/i, '');
  const label = baseName.length > 13 ? `${baseName.slice(0, 12)}…` : baseName;
  const labelWidth = Math.min(88, Math.max(42, label.length * 5.2 + 12));
  const placeLabelLeft = payload.growth > 15;
  const labelX = placeLabelLeft ? cx - 13 - labelWidth : cx + 13;
  return (
    <g className="benchmark-logo-marker">
      <circle cx={cx} cy={cy} r={10.5} fill="#ffffff" stroke={borderColor} strokeWidth={1.5} />
      <foreignObject x={cx - 7} y={cy - 7} width={14} height={14}>
        <div className="benchmark-logo-marker-inner">
          <CompanyLogoBadge companyId={payload.companyId} companyName={payload.companyName} size={14} />
        </div>
      </foreignObject>
      <g className="benchmark-logo-marker-label">
        <rect x={labelX} y={cy - 8} width={labelWidth} height={16} rx={4} fill="#ffffff" stroke={borderColor} strokeWidth={0.8} />
        <text x={labelX + 6} y={cy + 3} fill={borderColor}>{label}</text>
      </g>
    </g>
  );
}

function renderBenchmarkScatterMarker(props: unknown) {
  return <BenchmarkScatterMarker {...(props as BenchmarkScatterMarkerProps)} />;
}

export function CompanyComparisonV2Page() {
  const [reloadKey, setReloadKey] = useState(0);
  const state = useFinancialLeague(reloadKey);

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
  const averageCagr = filteredCompanies.length
    ? filteredCompanies.reduce((sum, company) => sum + company.revenueCagr, 0) / filteredCompanies.length
    : 0;
  const averageMargin = filteredCompanies.length
    ? filteredCompanies.reduce((sum, company) => sum + company.operatingMargin, 0) / filteredCompanies.length
    : 0;
  const averageDebtRatio = filteredCompanies.length
    ? filteredCompanies.reduce((sum, company) => sum + company.liabilitiesToAssets, 0) / filteredCompanies.length
    : 0;
  const officialRankByCompanyId = new Map(
    officialRankedCompanies.map(({ company, rank }) => [company.companyId, rank]),
  );
  const selectedCompanies = Array.from(selectedCompanyIds)
    .map((companyId) => filteredCompanies.find((company) => company.companyId === companyId))
    .filter((company): company is LeagueCompany => Boolean(company));
  const focusedCompany = filteredCompanies.find((company) => company.companyId === focusedCompanyId);
  const analysisCompany = selectedCompanies.length === 1
    ? selectedCompanies[0]
    : focusedCompany ?? officialRankedCompanies[0]?.company;
  const comparisonCompanies = selectedCompanies.length === 2 ? selectedCompanies : [];
  const analysisCandles = analysisCompany ? historicalCandles(analysisCompany) : [];
  const comparisonCandles = comparisonCompanies.map(historicalCandles);
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
        <strong>2021~2025 기업 실적 벤치마크 데이터를 분석하고 있습니다...</strong>
      </main>
    );
  }

  if (state.status === 'error') {
    return (
      <main className="financial-league-page league-loading" role="alert">
        <AlertCircle size={28} color="#dc2626" />
        <strong>데이터 로드 실패</strong>
        <p>{state.message}</p>
        <button type="button" onClick={() => setReloadKey((k) => k + 1)}>
          다시 시도
        </button>
      </main>
    );
  }

  return (
    <main className="financial-league-page" aria-label="기업 랭킹 리그 화면">
      <header className="league-page-heading">
        <div>
          <span className="league-page-eyebrow">FINANCIAL LEAGUE</span>
          <div className="league-page-title-row">
            <h1>AI 기업 비교</h1>
            <span>{filteredCompanies.length}개 기업</span>
          </div>
          <p>2021~2025 재무 성과를 동일 기준으로 비교하고 성장성·수익성·안정성을 함께 확인합니다.</p>
        </div>
      </header>

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
                    ['revenueCagr', '5개년 매출 성장률'],
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
                  const latest = latestHistoricalCandle(company);

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
                          aria-label={`5개년 매출 성장률 ${company.revenueCagr.toFixed(1)}%, ${company.revenueCagr > 0
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
                    <strong>2021~2025 매출 추이</strong>
                    <span>2021년=100 지수</span>
                  </div>
                  <div className="comparison-trend-legend">
                    <span><i className="is-a" />A {comparisonCompanies[0].displayName}</span>
                    <span><i className="is-b" />B {comparisonCompanies[1].displayName}</span>
                  </div>
                  <ComparisonTrendChart
                    first={indexedSeries(comparisonCandles[0].map((candle) => candle.revenue))}
                    second={indexedSeries(comparisonCandles[1].map((candle) => candle.revenue))}
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
                      <span>19개 기업 중 종합 {officialRankByCompanyId.get(analysisCompany.companyId)}위</span>
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
                    <strong>19개 기업 평균 대비</strong>
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
                    <strong>2021~2025 핵심 추이</strong>
                    <span>실적 방향성</span>
                  </div>
                  {[
                    { label: '매출', values: analysisCandles.map((candle) => candle.revenue), color: '#107c41', gradientId: 'revenue-trend-fill' },
                    { label: '영업이익', values: analysisCandles.map((candle) => candle.operatingIncome), color: '#2563eb', gradientId: 'profit-trend-fill' },
                  ].map((metric) => {
                    const change = percentChange(metric.values);
                    return (
                      <div className="single-trend-row" key={metric.label}>
                        <div>
                          <span>{metric.label}</span>
                          <strong>{formatAmount(metric.values[metric.values.length - 1] ?? 0, analysisCompany)}</strong>
                          <small className={change !== null && change < 0 ? 'is-down' : ''}>{change === null ? '—' : `${change >= 0 ? '+' : ''}${change.toFixed(1)}%`}</small>
                        </div>
                        <FinancialTrendChart
                          values={metric.values}
                          color={metric.color}
                          gradientId={metric.gradientId}
                          label={metric.label}
                          valueFormatter={(value) => formatAmount(value, analysisCompany)}
                        />
                      </div>
                    );
                  })}
                </div>
              </>
            ) : null}
          </section>

          <section className="interactive-distribution-panel position-analysis-panel" aria-label="기업군 내 성장성과 수익성 위치">
            <div className="distribution-title-row">
              <div>
                <span className="distribution-main-title">성장성 × 수익성 포지션</span>
                <p className="distribution-description">선택 기업이 전체 19개 기업에서 어디에 위치하는지 확인하세요.</p>
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
            <Database size={11} /> 데이터 출처: 파싱 기준기업 4개 + 재무 시나리오 기업 15개
          </span>
          <span className="footer-link-item">
            <RefreshCw size={11} /> 현재 순위: {RANKING_METRICS[rankingMetric].label} 기준 · {metricDirectionLabel}
          </span>
        </div>
        <div className="footer-right-time">
          <span className="footer-link-item">
            <Clock size={11} /> 최종 업데이트: {new Date(state.data.generatedAt).toLocaleString('ko-KR')}
          </span>
        </div>
      </footer>
    </main>
  );
}
