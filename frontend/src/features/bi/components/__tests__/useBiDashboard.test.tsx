import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DASHBOARD_FIXTURES } from '../../fixtures/dashboardFixtures';
import { useBiDashboard } from '../../hooks/useBiDashboard';
import {
  createBiMaterialization,
  fetchBiDashboard,
  fetchBiMaterializationJob,
} from '../../services/api';
import type { BiMaterializationJob } from '../../types';

const { refreshBiDashboardMock, fetchBiQuestionJobMock } = vi.hoisted(() => ({
  refreshBiDashboardMock: vi.fn(),
  fetchBiQuestionJobMock: vi.fn(),
}));

vi.mock('../../services/api', async (importOriginal) => ({
  ...await importOriginal<typeof import('../../services/api')>(),
  createBiMaterialization: vi.fn(),
  fetchBiDashboard: vi.fn(),
  fetchBiMaterializationJob: vi.fn(),
  refreshBiDashboard: refreshBiDashboardMock,
  fetchBiQuestionJob: fetchBiQuestionJobMock,
}));

const CURRENT_DASHBOARD = DASHBOARD_FIXTURES[0];
const NEXT_DASHBOARD = {
  ...CURRENT_DASHBOARD,
  snapshot: {
    ...CURRENT_DASHBOARD.snapshot,
    snapshotId: 'fixture-ready-002',
    generatedAt: '2026-08-20T12:00:00+09:00',
  },
} as const;

function job(status: BiMaterializationJob['status']): BiMaterializationJob {
  return {
    jobId: 'job-refresh',
    companyId: CURRENT_DASHBOARD.company.companyId,
    workbookHash: CURRENT_DASHBOARD.source.workbookHash,
    status,
    completedRequests: status === 'ready' ? 10 : 4,
    totalRequests: 10,
    publishedSnapshotId: status === 'ready' ? NEXT_DASHBOARD.snapshot.snapshotId : null,
    errorCode: status === 'failed' ? 'fixture.failed' : null,
    message: status === 'failed' ? '갱신 실패' : '처리 중',
    startedAt: '2026-08-20T10:00:00Z',
    updatedAt: '2026-08-20T10:01:00Z',
  };
}

function questionProgress(
  completedQuestions: number,
  failedQuestions = 0,
) {
  const totalQuestions = 10;
  return {
    jobId: 'question-job-refresh',
    totalQuestions,
    queuedQuestions: totalQuestions - completedQuestions - failedQuestions,
    runningQuestions: 0,
    completedQuestions,
    failedQuestions,
  };
}

describe('useBiDashboard refresh lifecycle', () => {
  beforeEach(() => {
    vi.mocked(createBiMaterialization).mockReset();
    vi.mocked(fetchBiDashboard).mockReset();
    vi.mocked(fetchBiMaterializationJob).mockReset();
    refreshBiDashboardMock.mockReset();
    fetchBiQuestionJobMock.mockReset();
  });

  it('keeps the current snapshot while a refresh is processing', async () => {
    // Given
    vi.mocked(fetchBiDashboard).mockResolvedValue({
      kind: 'snapshot',
      dashboard: CURRENT_DASHBOARD,
    });
    vi.mocked(createBiMaterialization).mockResolvedValue({
      jobId: 'job-refresh',
      status: 'queued',
      publishedSnapshotId: null,
    });
    vi.mocked(fetchBiMaterializationJob).mockResolvedValue(job('extracting'));
    refreshBiDashboardMock.mockResolvedValue(questionProgress(0));
    fetchBiQuestionJobMock.mockResolvedValue(questionProgress(4));
    const { result } = renderHook(() => useBiDashboard(CURRENT_DASHBOARD.company.companyId));
    await waitFor(() => expect(result.current.state.status).toBe('ready'));

    // When
    await act(async () => result.current.refresh());

    // Then
    await waitFor(() => {
      expect(result.current.state.status).toBe('ready');
      if (result.current.state.status !== 'ready') return;
      expect(result.current.state.dashboard.snapshot.snapshotId).toBe('fixture-ready-001');
      expect(result.current.state.dashboard.refresh.status).toBe('extracting');
    });
    expect(refreshBiDashboardMock).toHaveBeenCalledWith(
      CURRENT_DASHBOARD.company.companyId,
      expect.any(AbortSignal),
    );
  });

  it('atomically swaps to the published snapshot when refresh completes', async () => {
    // Given
    vi.mocked(fetchBiDashboard)
      .mockResolvedValueOnce({ kind: 'snapshot', dashboard: CURRENT_DASHBOARD })
      .mockResolvedValueOnce({ kind: 'snapshot', dashboard: NEXT_DASHBOARD });
    vi.mocked(createBiMaterialization).mockResolvedValue({
      jobId: 'job-refresh',
      status: 'queued',
      publishedSnapshotId: null,
    });
    vi.mocked(fetchBiMaterializationJob).mockResolvedValue(job('ready'));
    refreshBiDashboardMock.mockResolvedValue(questionProgress(0));
    fetchBiQuestionJobMock.mockResolvedValue(questionProgress(10));
    const { result } = renderHook(() => useBiDashboard(CURRENT_DASHBOARD.company.companyId));
    await waitFor(() => expect(result.current.state.status).toBe('ready'));

    // When
    await act(async () => result.current.refresh());

    // Then
    await waitFor(() => {
      expect(result.current.state.status).toBe('ready');
      if (result.current.state.status !== 'ready') return;
      expect(result.current.state.dashboard.snapshot.snapshotId).toBe('fixture-ready-002');
    });
  });

  it('keeps the current snapshot and reports a nonblocking refresh failure', async () => {
    // Given
    vi.mocked(fetchBiDashboard).mockResolvedValue({
      kind: 'snapshot',
      dashboard: CURRENT_DASHBOARD,
    });
    vi.mocked(createBiMaterialization).mockResolvedValue({
      jobId: 'job-refresh',
      status: 'queued',
      publishedSnapshotId: null,
    });
    vi.mocked(fetchBiMaterializationJob).mockResolvedValue(job('failed'));
    refreshBiDashboardMock.mockResolvedValue(questionProgress(0));
    fetchBiQuestionJobMock.mockRejectedValue(new Error('queue failed'));
    const { result } = renderHook(() => useBiDashboard(CURRENT_DASHBOARD.company.companyId));
    await waitFor(() => expect(result.current.state.status).toBe('ready'));

    // When
    await act(async () => result.current.refresh());

    // Then
    await waitFor(() => {
      expect(result.current.state.status).toBe('ready');
      if (result.current.state.status !== 'ready') return;
      expect(result.current.state.dashboard.snapshot.snapshotId).toBe('fixture-ready-001');
      expect(result.current.state.dashboard.refresh.status).toBe('failed');
    });
  });
});
