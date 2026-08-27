import { Activity, Database, RefreshCw, ShieldCheck, TrendingUp, X } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { FinancialCandlestickTerminal } from '../features/company-comparison-v2/FinancialCandlestickTerminal';
import { FinancialLeagueTable } from '../features/company-comparison-v2/FinancialLeagueTable';
import type { LeagueDistributionBucket, LeagueEvidence } from '../features/company-comparison-v2/leagueTypes';
import { RankingCriteriaPanel } from '../features/company-comparison-v2/RankingCriteriaPanel';
import { normalizedWeights, rankCompanies, RANKING_PRESETS } from '../features/company-comparison-v2/ranking';
import { useFinancialLeague } from '../features/company-comparison-v2/useFinancialLeague';
import '../features/company-comparison-v2/financial-league.css';

function Distribution({ title, average, buckets }: { readonly title: string; readonly average: number; readonly buckets: readonly LeagueDistributionBucket[] }) {
  const maximum = Math.max(1, ...buckets.map((item) => item.count));
  return <div className="distribution"><header><span>{title}</span><strong>평균 {average.toFixed(1)}%</strong></header><div className="distribution-bars">{buckets.map((item) => <div key={item.label}><i style={{ height: `${Math.max(8, item.count / maximum * 100)}%` }} /><span>{item.label}</span></div>)}</div></div>;
}

export function CompanyComparisonV2Page() {
  const [reloadKey, setReloadKey] = useState(0);
  const state = useFinancialLeague(reloadKey);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [activeEvidence, setActiveEvidence] = useState<LeagueEvidence | null>(null);
  const [rankingWeights, setRankingWeights] = useState(RANKING_PRESETS.balanced.weights);
  const [selectedYear, setSelectedYear] = useState(2028);

  useEffect(() => {
    if (state.status === 'ready' && selectedIds.size === 0) setSelectedIds(new Set(state.data.companies.slice(0, 3).map((item) => item.companyId)));
  }, [state, selectedIds.size]);

  const rankedCompanies = useMemo(() => state.status === 'ready' ? rankCompanies(state.data.companies, rankingWeights) : [], [rankingWeights, state]);
  const selectedCompanies = useMemo(() => rankedCompanies.filter((item) => selectedIds.has(item.companyId)).slice(0, 5), [rankedCompanies, selectedIds]);
  const toggle = (companyId: string) => setSelectedIds((current) => {
    const next = new Set(current);
    if (next.has(companyId)) next.delete(companyId);
    else if (next.size < 5) next.add(companyId);
    return next;
  });

  if (state.status === 'loading') return <main className="financial-league-page"><section className="league-loading"><RefreshCw className="spin" /><strong>재무 리그 엔진을 계산하고 있습니다</strong><span>18개 기업·시나리오의 8개 연도 데이터를 스코어링 중입니다.</span></section></main>;
  if (state.status === 'error') return <main className="financial-league-page"><section className="league-loading is-error"><Activity /><strong>리그 데이터를 불러오지 못했습니다</strong><span>{state.message}</span><button type="button" onClick={() => setReloadKey((key) => key + 1)}>다시 시도</button></section></main>;

  const { data } = state;
  const leader = rankedCompanies[0];
  const riser = [...rankedCompanies].sort((left, right) => right.rankChange - left.rankChange)[0];
  const normalized = normalizedWeights(rankingWeights);
  return <main className="financial-league-page">
    <header className="league-hero"><div><p>AI FINANCIAL INTELLIGENCE · LEAGUE TERMINAL</p><h1>다중 기업 재무 랭킹</h1><span>엑셀 실적과 예측 시나리오를 한 화면에서 스크리닝하고 트레이딩 차트처럼 비교합니다.</span></div><div className="league-hero-meta"><span><Database size={14} />{data.companies.length} 시나리오</span><span><ShieldCheck size={14} />근거 {data.evidence.length}건</span><button type="button" onClick={() => setReloadKey((key) => key + 1)}><RefreshCw size={14} /> 새로고침</button></div></header>
    <RankingCriteriaPanel weights={rankingWeights} onChange={setRankingWeights} />
    <section className="league-overview">
      <article className="spotlight-card spotlight-leader"><div><span>WEIGHTED RANK LEADER</span><TrendingUp size={20} /></div><strong><b>#1</b>{leader.displayName}</strong><p>가중 점수 {leader.compositeScore.toFixed(1)}점 · CAGR {leader.revenueCagr.toFixed(1)}%</p><div className="score-breakdown"><span>성장 {leader.growthScore.toFixed(0)}</span><span>수익 {leader.profitabilityScore.toFixed(0)}</span><span>안정 {leader.stabilityScore.toFixed(0)}</span></div></article>
      <article className="spotlight-card"><div><span>FASTEST RISER</span><Activity size={20} /></div><strong><b>▲{Math.max(0, riser.rankChange)}</b>{riser.displayName}</strong><p>실적 대비 예측 순위 · 현재 #{riser.rank}</p><div className="score-breakdown"><span>이전 #{riser.previousRank}</span><span>마진 {riser.operatingMargin.toFixed(1)}%</span><span>Tier {riser.tier}</span></div></article>
      <article className="distribution-card"><Distribution title="CAGR 분포" average={data.spotlight.averageCagr} buckets={data.spotlight.cagrDistribution} /></article>
      <article className="distribution-card"><Distribution title="마진 분포" average={data.spotlight.averageMargin} buckets={data.spotlight.marginDistribution} /></article>
    </section>
    <div className="league-workspace"><FinancialLeagueTable companies={rankedCompanies} selectedIds={selectedIds} onToggle={toggle} /><FinancialCandlestickTerminal companies={selectedCompanies} evidence={data.evidence} selectedYear={selectedYear} onYearChange={setSelectedYear} onEvidence={setActiveEvidence} /></div>
    <footer className="league-methodology"><ShieldCheck size={15} /><span><strong>현재 판단 기준</strong> = 성장성 {normalized.growth.toFixed(0)}% + 수익성 {normalized.profitability.toFixed(0)}% + 안정성 {normalized.stability.toFixed(0)}%</span><span>마지막 계산 {new Date(data.generatedAt).toLocaleString('ko-KR')}</span></footer>
    {activeEvidence ? <div className="evidence-backdrop" role="presentation" onMouseDown={() => setActiveEvidence(null)}><section className="evidence-modal" role="dialog" aria-modal="true" aria-labelledby="evidence-title" onMouseDown={(event) => event.stopPropagation()}><header><div><span>EXCEL SOURCE EVIDENCE</span><h2 id="evidence-title">{activeEvidence.sheetName}!{activeEvidence.cellCoord}</h2></div><button type="button" onClick={() => setActiveEvidence(null)} aria-label="닫기"><X /></button></header><dl><div><dt>파일</dt><dd>{activeEvidence.fileName}</dd></div><div><dt>원본 위치</dt><dd>{activeEvidence.sheetName}!{activeEvidence.cellCoord}</dd></div><div><dt>출처</dt><dd>{activeEvidence.origin === 'rag' ? 'RAG 검색 근거' : 'BI 스냅샷'}</dd></div></dl><blockquote>{activeEvidence.sourceText}</blockquote></section></div> : null}
  </main>;
}
