import {
  AlertCircle,
  BarChart3,
  CheckCircle2,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  TrendingUp,
  WalletCards,
} from 'lucide-react';
import { useEffect, useMemo, useState, type CSSProperties } from 'react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  buildComparisonViewModel,
  COMPARISON_COMPANIES,
  getCommonFiscalYears,
  presentNetDebt,
  type ComparisonCompanyKey,
  type CompanyComparisonResult,
  type ComparisonInsight,
} from '../features/company-comparison/comparison';
import { useCompanyComparison } from '../features/company-comparison/useCompanyComparison';
import '../features/company-comparison/company-comparison.css';

type ChartMetric = 'revenue' | 'operatingIncome';

function formatPercent(value: number): string {
  return `${value.toFixed(1)}%`;
}

function formatAmount(value: number): string {
  return value.toLocaleString('ko-KR', { maximumFractionDigits: 1 });
}

function insightIcon(type: ComparisonInsight['type']) {
  if (type === 'growth') return TrendingUp;
  if (type === 'profitability') return WalletCards;
  return ShieldAlert;
}

function MetricComparisonList({
  title,
  description,
  companies,
  valueOf,
  formatValue,
  lowerIsBetter = false,
}: {
  readonly title: string;
  readonly description: string;
  readonly companies: readonly CompanyComparisonResult[];
  readonly valueOf: (company: CompanyComparisonResult) => number;
  readonly formatValue: (value: number) => string;
  readonly lowerIsBetter?: boolean;
}) {
  const values = companies.map(valueOf);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const strength = (value: number) => {
    if (min === max) return 1;
    return lowerIsBetter ? (max - value) / (max - min) : (value - min) / (max - min);
  };

  return (
    <div className="comparison-breakdown">
      <div className="comparison-breakdown__title">
        <div><strong>{title}</strong><span>{description}</span></div>
        <small>{lowerIsBetter ? '낮을수록 양호' : '높을수록 양호'}</small>
      </div>
      <div className="comparison-breakdown__rows">
        {companies.map((company) => (
          <div className="comparison-breakdown__row" key={company.key}>
            <span className="comparison-breakdown__company"><i style={{ backgroundColor: company.color }} />{company.label}</span>
            <span className="comparison-breakdown__bar"><i style={{ '--bar-color': company.color, '--bar-width': `${24 + strength(valueOf(company)) * 76}%` } as CSSProperties} /></span>
            <strong>{formatValue(valueOf(company))}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}

function stabilityStatus(liabilitiesToAssets: number): { readonly label: string; readonly tone: 'stable' | 'caution' | 'risk' } {
  if (liabilitiesToAssets < 50) return { label: '안정', tone: 'stable' };
  if (liabilitiesToAssets < 70) return { label: '주의', tone: 'caution' };
  return { label: '위험', tone: 'risk' };
}

function StabilityOverview({
  companies,
  endYear,
  currency,
}: {
  readonly companies: readonly CompanyComparisonResult[];
  readonly endYear: number;
  readonly currency: string;
}) {
  return (
    <div className="comparison-stability-overview">
      <div className="comparison-stability-legend">
        <span><i className="is-stable" />50% 미만 안정</span>
        <span><i className="is-caution" />50–70% 주의</span>
        <span><i className="is-risk" />70% 이상 위험</span>
      </div>
      {companies.map((company) => {
        const status = stabilityStatus(company.liabilitiesToAssets);
        const netDebt = presentNetDebt(company.netDebt);
        return (
          <article className={`comparison-stability-company comparison-stability-company--${status.tone}`} key={company.key}>
            <header>
              <span><i style={{ backgroundColor: company.color }} />{company.label}</span>
              <strong>{status.label}</strong>
            </header>
            <div className="comparison-stability-values">
              <div><span>총부채 / 총자산</span><b>{formatPercent(company.liabilitiesToAssets)}</b><small>{endYear}년</small></div>
              <div><span>{netDebt.label}</span><b>{formatAmount(netDebt.value)}</b><small>{currency} 백만</small></div>
            </div>
            <p>{netDebt.description}</p>
          </article>
        );
      })}
      <p className="comparison-stability-note">상태는 총부채/총자산 비율 기준이며, 순부채를 함께 확인해 현금 여력을 보완적으로 해석합니다.</p>
    </div>
  );
}

export function CompanyComparisonPage() {
  const [reloadKey, setReloadKey] = useState(0);
  const [chartMetric, setChartMetric] = useState<ChartMetric>('revenue');
  const [selectedCompanyKeys, setSelectedCompanyKeys] = useState<readonly ComparisonCompanyKey[]>(
    () => COMPARISON_COMPANIES.map((company) => company.key),
  );
  const loadState = useCompanyComparison(reloadKey);
  const companies = loadState.status === 'ready' ? loadState.companies : [];
  const selectedCompanies = useMemo(
    () => companies.filter((company) => selectedCompanyKeys.includes(company.key)),
    [companies, selectedCompanyKeys],
  );
  const commonYears = useMemo(() => getCommonFiscalYears(selectedCompanies), [selectedCompanies]);
  const [startYear, setStartYear] = useState<number | null>(null);
  const [endYear, setEndYear] = useState<number | null>(null);

  useEffect(() => {
    if (commonYears.length < 2) return;
    setStartYear((current) => current !== null && commonYears.includes(current) && current < commonYears[commonYears.length - 1]
      ? current : commonYears[0]);
    setEndYear((current) => current !== null && commonYears.includes(current) && current > commonYears[0]
      ? current : commonYears[commonYears.length - 1]);
  }, [commonYears]);

  const modelResult = useMemo(() => {
    if (loadState.status !== 'ready' || startYear === null || endYear === null) return null;
    try {
      return { model: buildComparisonViewModel(selectedCompanies, startYear, endYear), error: null };
    } catch (error) {
      return { model: null, error: error instanceof Error ? error.message : '비교 지표 계산에 실패했습니다.' };
    }
  }, [endYear, loadState.status, selectedCompanies, startYear]);
  const model = modelResult?.model ?? null;
  const chartData = model ? model.companies[0].points.map((point) => {
    const row: Record<string, number> = { year: point.year };
    for (const company of model.companies) {
      const companyPoint = company.points.find((candidate) => candidate.year === point.year);
      if (companyPoint) row[company.key] = companyPoint[chartMetric];
    }
    return row;
  }) : [];

  return (
    <main className="company-comparison-page">
      <header className="company-comparison-header">
        <div><p className="company-comparison-eyebrow">FINANCIAL INTELLIGENCE</p><h1>기업 비교 인사이트</h1><p>검증된 3개 기업 중 원하는 2~3개를 같은 기간 기준으로 비교합니다.</p></div>
        <button className="comparison-refresh-button" type="button" onClick={() => setReloadKey((value) => value + 1)} disabled={loadState.status === 'loading'}><RefreshCw size={16} />분석 새로고침</button>
      </header>

      {loadState.status === 'loading' && <section className="comparison-state-card" aria-live="polite"><RefreshCw className="comparison-spin" size={24} /><strong>3개 기업의 검증된 스냅샷을 불러오고 있습니다.</strong></section>}
      {loadState.status === 'error' && <section className="comparison-state-card comparison-state-card--error" role="alert"><AlertCircle size={24} /><div><strong>기업 비교 데이터를 준비하지 못했습니다.</strong><p>{loadState.message}</p></div></section>}
      {loadState.status === 'ready' && commonYears.length < 2 && <section className="comparison-state-card comparison-state-card--error" role="alert"><AlertCircle size={24} /><strong>세 기업에 공통으로 존재하는 회계연도가 2개 미만입니다.</strong></section>}
      {modelResult?.error && <section className="comparison-state-card comparison-state-card--error" role="alert"><AlertCircle size={24} /><strong>{modelResult.error}</strong></section>}

      {model && <>
        <section className="comparison-toolbar" aria-label="비교 조건">
          <div className="comparison-company-chips">
            <span className="comparison-toolbar-label">비교 기업 <b>{selectedCompanyKeys.length}/3</b></span>
            {companies.map((company) => {
              const selected = selectedCompanyKeys.includes(company.key);
              const minimumSelected = selected && selectedCompanyKeys.length === 2;
              return (
                <button
                  className={`comparison-company-chip ${selected ? 'is-selected' : ''}`}
                  type="button"
                  key={company.key}
                  aria-pressed={selected}
                  disabled={minimumSelected}
                  title={minimumSelected ? '비교 기업은 최소 2개가 필요합니다.' : undefined}
                  onClick={() => setSelectedCompanyKeys((current) => selected
                    ? current.filter((key) => key !== company.key)
                    : [...current, company.key])}
                >
                  <i style={{ backgroundColor: company.color }} />{company.label}
                </button>
              );
            })}
          </div>
          <div className="comparison-period-controls"><span className="comparison-toolbar-label">기간</span>
            <select aria-label="비교 시작 연도" value={model.startYear} onChange={(event) => {
              const value = Number(event.target.value); setStartYear(value);
              if (endYear !== null && value >= endYear) setEndYear(commonYears.find((year) => year > value) ?? commonYears[commonYears.length - 1]);
            }}>{commonYears.slice(0, -1).map((year) => <option key={year} value={year}>{year}</option>)}</select><span>–</span>
            <select aria-label="비교 종료 연도" value={model.endYear} onChange={(event) => setEndYear(Number(event.target.value))}>{commonYears.filter((year) => year > model.startYear).map((year) => <option key={year} value={year}>{year}</option>)}</select>
          </div>
        </section>

        <div className="comparison-dashboard-grid">
          <div className="comparison-main-column">
            <section className="comparison-card comparison-chart-card">
              <div className="comparison-chart-header">
                <div><h2>실적 추이 비교</h2><p>{model.startYear}–{model.endYear} · {model.companies[0].currency} {model.companies[0].scale === 'millions' ? '백만' : model.companies[0].scale}</p></div>
                <div className="comparison-chart-tabs" role="group" aria-label="차트 지표 선택">
                  <button className={chartMetric === 'revenue' ? 'is-active' : ''} type="button" onClick={() => setChartMetric('revenue')}>매출</button>
                  <button className={chartMetric === 'operatingIncome' ? 'is-active' : ''} type="button" onClick={() => setChartMetric('operatingIncome')}>영업이익</button>
                </div>
              </div>
              <p className="comparison-chart-guide">{chartMetric === 'revenue' ? '기업별 매출 규모와 성장 흐름을 비교합니다.' : '기업별 본업의 이익 규모와 적자 여부를 비교합니다.'}</p>
              <div className="comparison-chart-wrap"><ResponsiveContainer width="100%" height="100%"><LineChart data={chartData} margin={{ top: 12, right: 18, left: 4, bottom: 0 }}>
                <CartesianGrid stroke="#e7eee9" strokeDasharray="3 4" vertical={false} /><XAxis dataKey="year" tickLine={false} axisLine={false} tick={{ fill: '#64746b', fontSize: 12 }} />
                <YAxis tickLine={false} axisLine={false} width={58} tick={{ fill: '#64746b', fontSize: 11 }} tickFormatter={formatAmount} /><Tooltip formatter={(value) => [`${formatAmount(Number(value))} ${model.companies[0].currency} 백만`, chartMetric === 'revenue' ? '매출' : '영업이익']} labelFormatter={(year) => `${year}년`} /><Legend iconType="circle" wrapperStyle={{ fontSize: 11, paddingTop: 10 }} />
                {model.companies.map((company) => <Line key={company.key} name={company.label} type="monotone" dataKey={company.key} stroke={company.color} strokeWidth={2.6} dot={{ r: 3.5, strokeWidth: 2, fill: '#fff' }} activeDot={{ r: 5 }} />)}
              </LineChart></ResponsiveContainer></div>
            </section>

            <div className="comparison-summary-grid">
              <section className="comparison-card comparison-metrics-card">
                <div className="comparison-card-heading"><div><h2>성장률과 수익성</h2><p>성장 속도와 종료연도 수익 효율을 구분해 비교합니다.</p></div><BarChart3 size={18} /></div>
                <div className="comparison-breakdown-stack">
                  <MetricComparisonList title="매출 성장률" description={`${model.startYear}–${model.endYear} CAGR`} companies={model.companies} valueOf={(company) => company.revenueCagr} formatValue={formatPercent} />
                  <MetricComparisonList title="영업이익률" description={`${model.endYear}년 영업이익 ÷ 매출`} companies={model.companies} valueOf={(company) => company.operatingMargin} formatValue={formatPercent} />
                </div>
              </section>
              <section className="comparison-card comparison-metrics-card">
                <div className="comparison-card-heading"><div><h2>재무 안정성 진단</h2><p>기업별 차입 부담과 현금 여력을 하나의 상태로 확인합니다.</p></div><ShieldAlert size={18} /></div>
                <StabilityOverview companies={model.companies} endYear={model.endYear} currency={model.companies[0].currency} />
              </section>
            </div>

            <section className="comparison-card comparison-evidence-card"><div className="comparison-card-heading"><div><h2>근거 및 출처</h2><p>브리프 번호와 연결된 원본 셀 기준</p></div><CheckCircle2 size={18} /></div><div className="comparison-table-wrap"><table><thead><tr><th>근거</th><th>지표</th><th>기준일</th><th>출처</th><th>검증</th></tr></thead><tbody>{model.evidenceRows.map((row) => <tr key={row.id}><td>[{row.id}]</td><td>{row.metric}</td><td>{row.basis}</td><td title={row.sources.join(', ')}>{row.sources.length}개 기업 파일 · 원본 셀 {row.evidence.length}개</td><td><span className="comparison-verified"><CheckCircle2 size={13} />검증 완료</span></td></tr>)}</tbody></table></div></section>
          </div>

          <aside className="comparison-side-column">
            <section className="comparison-card comparison-brief-card"><div className="comparison-card-heading"><div><h2><Sparkles size={19} /> AI 비교 브리프</h2><p>검증된 원본 지표와 계산식에 기반한 상세 해석</p></div></div><div className="comparison-insights">{model.insights.map((insight) => { const Icon = insightIcon(insight.type); return <article className={`comparison-insight comparison-insight--${insight.type}`} key={insight.type}><div><Icon size={17} /><strong>{insight.title}</strong></div><p>{insight.body}</p><span>연결 근거 {insight.evidenceIds.map((id) => `[${id}]`).join(' ')}</span></article>; })}</div></section>
          </aside>
        </div>
      </>}
    </main>
  );
}
