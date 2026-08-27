import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { DASHBOARD_FIXTURES } from '../../../../test/fixtures/biDashboardFixtures';
import { useSelectedBiCompany } from '../useSelectedBiCompany';

const STORAGE_KEY = 'rag-flow:bi-selected-company:v1';
const COMPANIES = DASHBOARD_FIXTURES.map((dashboard) => ({
  companyId: dashboard.company.companyId,
  displayName: dashboard.company.displayName,
  source: dashboard.source,
  currentSnapshotId: dashboard.snapshot.snapshotId,
  snapshotStatus: dashboard.snapshot.status,
  refreshStatus: dashboard.refresh.status,
  updatedAt: dashboard.snapshot.generatedAt,
}));

describe('useSelectedBiCompany', () => {
  beforeEach(() => localStorage.clear());

  it('uses the stored company only while it remains available', () => {
    localStorage.setItem(STORAGE_KEY, 'missing-company');

    const { result, rerender } = renderHook(
      ({ companies }) => useSelectedBiCompany(companies),
      { initialProps: { companies: COMPANIES } },
    );

    expect(result.current.selectedCompanyId).toBe(COMPANIES[0]?.companyId);

    rerender({ companies: COMPANIES.slice(1) });

    expect(result.current.selectedCompanyId).toBe(COMPANIES[1]?.companyId);
  });

  it('persists an explicit company selection', () => {
    const { result } = renderHook(() => useSelectedBiCompany(COMPANIES));

    act(() => result.current.selectCompany(COMPANIES[1]?.companyId ?? ''));

    expect(result.current.selectedCompanyId).toBe(COMPANIES[1]?.companyId);
    expect(localStorage.getItem(STORAGE_KEY)).toBe(COMPANIES[1]?.companyId);
  });
});
