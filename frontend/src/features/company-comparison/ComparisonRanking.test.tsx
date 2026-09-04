import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ComparisonRankingToolbar } from './ComparisonRanking';

const defaultProps = {
  activeRankingLabel: '종합점수 순위',
  metricDirectionLabel: '높은 순',
  onMetricChange: vi.fn(),
  onReset: vi.fn(),
  onRefresh: vi.fn(),
} as const;

describe('ComparisonRankingToolbar', () => {
  it('hides the live sorting pill for the default ranking', () => {
    render(
      <ComparisonRankingToolbar
        {...defaultProps}
        rankingMetric="composite"
        displayDirection="best-first"
      />,
    );

    expect(screen.queryByRole('button', { name: '기본 정렬로 초기화' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '스냅샷 새로고침' })).toBeInTheDocument();
  });

  it('shows a resettable live sorting pill for a changed ranking', () => {
    const onReset = vi.fn();
    render(
      <ComparisonRankingToolbar
        {...defaultProps}
        rankingMetric="revenue"
        displayDirection="best-first"
        activeRankingLabel="매출액 순위"
        onReset={onReset}
      />,
    );

    expect(screen.getByText('매출액 순위 · 높은 순')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '기본 정렬로 초기화' }));
    expect(onReset).toHaveBeenCalledOnce();
  });

  it('shows the pill when the composite ranking direction is reversed', () => {
    render(
      <ComparisonRankingToolbar
        {...defaultProps}
        rankingMetric="composite"
        displayDirection="worst-first"
        metricDirectionLabel="낮은 순"
      />,
    );

    expect(screen.getByText('종합점수 순위 · 낮은 순')).toBeInTheDocument();
  });
});
