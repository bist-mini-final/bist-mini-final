import { ArrowDown, ArrowUp, ArrowUpDown, Minus } from 'lucide-react';
import { useMemo, useState } from 'react';
import type { LeagueCompany } from './leagueTypes';

type Filter = 'all' | 'growth' | 'margin' | 'stable';
type SortKey = 'rank' | 'compositeScore' | 'rankChange' | 'revenueCagr' | 'operatingMargin' | 'stabilityScore';

const FILTERS: readonly { key: Filter; label: string }[] = [
  { key: 'all', label: '전체' }, { key: 'growth', label: '성장률 상위 10%' },
  { key: 'margin', label: '마진 20% 이상' }, { key: 'stable', label: '무차입 / 안정 기업' },
];

export function FinancialLeagueTable({ companies, selectedIds, onToggle }: {
  readonly companies: readonly LeagueCompany[];
  readonly selectedIds: ReadonlySet<string>;
  readonly onToggle: (companyId: string) => void;
}) {
  const [filter, setFilter] = useState<Filter>('all');
  const [sort, setSort] = useState<{ key: SortKey; direction: 'asc' | 'desc' }>({ key: 'rank', direction: 'asc' });
  const growthIds = useMemo(() => new Set([...companies].sort((a, b) => b.revenueCagr - a.revenueCagr).slice(0, Math.max(1, Math.ceil(companies.length * 0.1))).map((item) => item.companyId)), [companies]);
  const visible = useMemo(() => companies.filter((company) => (
    filter === 'all' || (filter === 'growth' && growthIds.has(company.companyId))
    || (filter === 'margin' && company.operatingMargin >= 20)
    || (filter === 'stable' && (company.netDebt <= 0 || company.liabilitiesToAssets <= 30))
  )).sort((a, b) => {
    const difference = a[sort.key] - b[sort.key];
    return sort.direction === 'asc' ? difference : -difference;
  }), [companies, filter, growthIds, sort]);

  const changeSort = (key: SortKey) => setSort((current) => ({ key, direction: current.key === key && current.direction === 'desc' ? 'asc' : 'desc' }));
  const sortHeader = (label: string, key: SortKey) => (
    <button type="button" onClick={() => changeSort(key)}>{label}<ArrowUpDown size={12} aria-hidden="true" /></button>
  );

  return (
    <section className="league-panel league-table-panel">
      <div className="league-panel-heading">
        <div><span>FINANCIAL SCREENER</span><h2>재무 리그 테이블</h2><p>실적 2021–2025 · 예측 2026–2028 · 최대 5개 오버레이</p></div>
        <strong>{visible.length} / {companies.length}</strong>
      </div>
      <div className="league-filter-row" role="group" aria-label="리그 필터">
        {FILTERS.map((item) => <button type="button" className={filter === item.key ? 'is-active' : ''} key={item.key} onClick={() => setFilter(item.key)}>{item.label}</button>)}
      </div>
      <div className="league-table-scroll">
        <table>
          <thead><tr><th aria-label="차트 선택" /><th>{sortHeader('순위', 'rank')}</th><th>기업 / 시나리오</th><th>{sortHeader('랭킹 스코어', 'compositeScore')}</th><th>{sortHeader('변동', 'rankChange')}</th><th>{sortHeader('매출 CAGR', 'revenueCagr')}</th><th>{sortHeader('영업이익률', 'operatingMargin')}</th><th>{sortHeader('안전 등급', 'stabilityScore')}</th></tr></thead>
          <tbody>{visible.map((company) => {
            const selected = selectedIds.has(company.companyId);
            return <tr key={company.companyId} className={selected ? 'is-selected' : ''}>
              <td><input type="checkbox" checked={selected} onChange={() => onToggle(company.companyId)} aria-label={`${company.displayName} 차트 선택`} /></td>
              <td><b className="league-rank">{company.rank}</b></td>
              <td><div className="league-company"><strong>{company.displayName}</strong></div></td>
              <td><div className="league-score"><strong>{company.compositeScore.toFixed(1)}</strong><span><i style={{ width: `${company.compositeScore}%` }} /></span></div></td>
              <td><span className={`rank-change ${company.rankChange > 0 ? 'is-up' : company.rankChange < 0 ? 'is-down' : ''}`}>{company.rankChange > 0 ? <ArrowUp size={12} /> : company.rankChange < 0 ? <ArrowDown size={12} /> : <Minus size={12} />}{company.rankChange === 0 ? '0' : Math.abs(company.rankChange)}</span></td>
              <td className={company.revenueCagr >= 15 ? 'metric-positive' : ''}>{company.revenueCagr.toFixed(1)}%</td>
              <td>{company.operatingMargin.toFixed(1)}%</td>
              <td><span className={`tier-badge tier-${company.tier.toLowerCase()}`}>{company.tier}</span><small>{company.stabilityScore.toFixed(0)}</small></td>
            </tr>;
          })}</tbody>
        </table>
      </div>
    </section>
  );
}
