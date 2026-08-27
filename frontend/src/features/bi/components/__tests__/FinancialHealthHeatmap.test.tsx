import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { DASHBOARD_FIXTURES } from '../../../../test/fixtures/biDashboardFixtures';
import { FinancialHealthHeatmap } from '../charts/FinancialHealthHeatmap';

describe('FinancialHealthHeatmap', () => {
  it('renders the financial health matrix as an accessible chart', () => {
    render(
      <FinancialHealthHeatmap
        dashboard={DASHBOARD_FIXTURES[0]}
        range="최근 5개"
        size="L"
      />,
    );

    expect(screen.getByRole('img', { name: '기간별 재무 체력 히트맵' })).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });
});
