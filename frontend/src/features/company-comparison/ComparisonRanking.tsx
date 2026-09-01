import { ArrowUpDown, ChevronDown, RefreshCw, X } from 'lucide-react';
import { AppLink } from '../../app/router';
import { Button } from '../../shared/ui';
import { formatAmount, formatCompositeScore } from './analysis';
import {
  latestHistoricalPeriod,
  type DisplayDirection,
  type RankedCompany,
  type RankingMetric,
} from './metricRanking';
import { CompanyLogoBadge } from './CompanyLogoBadge';

const FACTOR_LABELS: Record<'Overall' | 'Revenue' | 'Profit' | 'Growth', string> = {
  Overall: '종합순위',
  Revenue: '매출액',
  Profit: '영업이익',
  Growth: '성장률',
};

const FACTOR_METRICS: Record<keyof typeof FACTOR_LABELS, RankingMetric> = {
  Overall: 'composite',
  Revenue: 'revenue',
  Profit: 'operatingIncome',
  Growth: 'revenueCagr',
};

interface ComparisonRankingToolbarProps {
  readonly rankingMetric: RankingMetric;
  readonly activeRankingLabel: string;
  readonly metricDirectionLabel: string;
  readonly onMetricChange: (metric: RankingMetric) => void;
  readonly onReset: () => void;
  readonly onRefresh: () => void;
}

export function ComparisonRankingToolbar({
  rankingMetric,
  activeRankingLabel,
  metricDirectionLabel,
  onMetricChange,
  onReset,
  onRefresh,
}: ComparisonRankingToolbarProps) {
  return (
    <section className="league-top-filter-bar" aria-label="순위 정렬 제어">
      <div className="filter-section-block">
        <span className="filter-section-label">빠른 표시 정렬</span>
        <div className="filter-pills-row">
          {(Object.keys(FACTOR_LABELS) as (keyof typeof FACTOR_LABELS)[]).map((factor) => {
            const metric = FACTOR_METRICS[factor];
            const isActive = rankingMetric === metric;
            return (
              <button
                type="button"
                key={factor}
                className={`dropdown-filter-pill ${isActive ? 'is-active' : ''}`}
                onClick={() => onMetricChange(metric)}
                aria-pressed={isActive}
              >
                <span>{FACTOR_LABELS[factor]}</span>
                <ChevronDown size={11} />
              </button>
            );
          })}
        </div>
      </div>

      <div className="filter-section-block">
        <span className="filter-section-label">실시간 정렬 기준</span>
        <div className="filter-pills-row">
          <div className="sort-status-pill">
            <ArrowUpDown size={11} />
            <span>{activeRankingLabel} · {metricDirectionLabel}</span>
            <button
              type="button"
              className="sort-clear-btn"
              onClick={onReset}
              aria-label="정렬 초기화"
              title="정렬 초기화"
            >
              <X size={10} />
            </button>
          </div>
          <Button type="button" onClick={onRefresh}>
            <RefreshCw size={14} /> 스냅샷 새로고침
          </Button>
        </div>
      </div>
    </section>
  );
}

interface CompanyRankingTableProps {
  readonly companies: readonly RankedCompany[];
  readonly rankingMetric: RankingMetric;
  readonly displayDirection: DisplayDirection;
  readonly activeRankingLabel: string;
  readonly focusedCompanyId: string;
  readonly selectedCompanyIds: ReadonlySet<string>;
  readonly onMetricChange: (metric: RankingMetric) => void;
  readonly onFocusCompany: (companyId: string) => void;
  readonly onToggleCompany: (companyId: string) => void;
}

const TABLE_METRICS = [
  ['revenue', '매출액'],
  ['operatingIncome', '영업이익'],
  ['revenueCagr', '관측 구간 매출 성장률'],
  ['operatingMargin', '영업이익률'],
] as const;

function SortIndicator({
  active,
  direction,
}: {
  readonly active: boolean;
  readonly direction: DisplayDirection;
}) {
  return <span aria-hidden="true">{active ? (direction === 'best-first' ? '▼' : '▲') : '↕'}</span>;
}

export function CompanyRankingTable({
  companies,
  rankingMetric,
  displayDirection,
  activeRankingLabel,
  focusedCompanyId,
  selectedCompanyIds,
  onMetricChange,
  onFocusCompany,
  onToggleCompany,
}: CompanyRankingTableProps) {
  return (
    <div className="league-table-card">
      <div className="league-table-scroll-wrap">
        <table className="league-pixel-table">
          <thead>
            <tr>
              <th className="col-th-rank">{activeRankingLabel}</th>
              <th className="col-th-select">비교</th>
              <th className="col-th-company">기업명</th>
              {TABLE_METRICS.map(([metric, label]) => (
                <th
                  key={metric}
                  className={`metric-rank-header col-th-${metric} ${rankingMetric === metric ? 'is-active' : ''}`}
                  aria-sort={rankingMetric === metric
                    ? (displayDirection === 'best-first' ? 'descending' : 'ascending')
                    : 'none'}
                >
                  <button type="button" onClick={() => onMetricChange(metric)}>
                    {label}
                    <SortIndicator active={rankingMetric === metric} direction={displayDirection} />
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
                <button type="button" onClick={() => onMetricChange('composite')}>
                  종합점수
                  <SortIndicator active={rankingMetric === 'composite'} direction={displayDirection} />
                </button>
              </th>
            </tr>
          </thead>
          <tbody>
            {companies.map(({ company, rank }) => {
              const isFocused = company.companyId === focusedCompanyId;
              const isSelected = selectedCompanyIds.has(company.companyId);
              const latest = latestHistoricalPeriod(company);

              return (
                <tr
                  key={company.companyId}
                  className={`league-table-row ${isFocused ? 'is-selected' : ''}`}
                  onClick={() => onFocusCompany(company.companyId)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault();
                      onFocusCompany(company.companyId);
                    }
                  }}
                  tabIndex={0}
                  aria-selected={isFocused}
                >
                  <td className="col-th-rank"><div className="rank-cell-display"><span>{rank}</span></div></td>
                  <td className="col-th-select">
                    <input
                      type="checkbox"
                      checked={isSelected}
                      aria-label={`${company.displayName} 비교 선택`}
                      onClick={(event) => event.stopPropagation()}
                      onChange={() => onToggleCompany(company.companyId)}
                    />
                  </td>
                  <td className="col-th-company">
                    <div className="company-cell-flex">
                      <CompanyLogoBadge companyId={company.companyId} companyName={company.displayName} size={27} />
                      <AppLink
                        to={`/dashboard?companyId=${encodeURIComponent(company.companyId)}`}
                        className="company-name-text"
                        onClick={(event) => event.stopPropagation()}
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
                      <span className={`tier-round-pill pill-${company.tier.toLowerCase()}`}>{company.tier}</span>
                      <strong>{formatCompositeScore(company.compositeScore)}</strong>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="league-mobile-ranking" aria-label={`${activeRankingLabel} 모바일 순위 목록`}>
        {companies.map(({ company, rank }) => {
          const isFocused = company.companyId === focusedCompanyId;
          const isSelected = selectedCompanyIds.has(company.companyId);
          return (
            <article
              key={company.companyId}
              className={`league-mobile-company${isFocused ? ' is-selected' : ''}`}
            >
              <header className="league-mobile-company__header">
                <span className="league-mobile-company__rank">{rank}</span>
                <button
                  type="button"
                  className="league-mobile-company__identity"
                  onClick={() => onFocusCompany(company.companyId)}
                  aria-pressed={isFocused}
                >
                  <CompanyLogoBadge companyId={company.companyId} companyName={company.displayName} size={32} />
                  <span className="league-mobile-company__name">{company.displayName}</span>
                </button>
                <span className="league-mobile-company__summary" title="종합 점수">
                  <span className={`tier-round-pill pill-${company.tier.toLowerCase()}`}>{company.tier}</span>
                  <strong>{formatCompositeScore(company.compositeScore)}</strong>
                </span>
                <label className="league-mobile-company__compare">
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => onToggleCompany(company.companyId)}
                  />
                  비교
                </label>
              </header>
            </article>
          );
        })}
      </div>
    </div>
  );
}
