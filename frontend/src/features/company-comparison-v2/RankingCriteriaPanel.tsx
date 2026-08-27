import { Gauge, SlidersHorizontal } from 'lucide-react';
import { RANKING_PRESETS, normalizedWeights, type RankingPreset, type RankingWeights } from './ranking';

const DIMENSIONS = [
  { key: 'growth', label: '성장성', description: '예측 매출 CAGR' },
  { key: 'profitability', label: '수익성', description: '예측 영업이익률' },
  { key: 'stability', label: '안정성', description: '부채비율·순현금' },
] as const;

export function RankingCriteriaPanel({ weights, onChange }: {
  readonly weights: RankingWeights;
  readonly onChange: (weights: RankingWeights) => void;
}) {
  const normalized = normalizedWeights(weights);
  const activePreset = (Object.entries(RANKING_PRESETS) as [RankingPreset, (typeof RANKING_PRESETS)[RankingPreset]][]).find(([, preset]) => (
    preset.weights.growth === weights.growth
    && preset.weights.profitability === weights.profitability
    && preset.weights.stability === weights.stability
  ))?.[0];
  return <section className="ranking-criteria-panel" aria-label="랭킹 판단 기준 설정">
    <header><div><span><SlidersHorizontal size={14} /> RANKING CRITERIA</span><h2>랭킹 판단 기준</h2><p>중요하게 볼 재무 관점을 선택하면 점수와 순위가 즉시 다시 계산됩니다.</p></div><div className="ranking-formula"><Gauge size={16} /><span>가중 합산</span><strong>100점</strong></div></header>
    <div className="ranking-presets" role="group" aria-label="랭킹 기준 프리셋">{(Object.entries(RANKING_PRESETS) as [RankingPreset, (typeof RANKING_PRESETS)[RankingPreset]][]).map(([key, preset]) => <button type="button" key={key} className={activePreset === key ? 'is-active' : ''} onClick={() => onChange(preset.weights)}>{preset.label}</button>)}</div>
    <div className="ranking-sliders">{DIMENSIONS.map((dimension) => <label key={dimension.key}><span><b>{dimension.label}</b><small>{dimension.description}</small></span><input type="range" min="0" max="100" step="5" value={weights[dimension.key]} onChange={(event) => onChange({ ...weights, [dimension.key]: Number(event.target.value) })} /><strong>{normalized[dimension.key].toFixed(0)}%</strong></label>)}</div>
  </section>;
}
