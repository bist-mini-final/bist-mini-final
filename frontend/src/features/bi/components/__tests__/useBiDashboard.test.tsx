import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DASHBOARD_FIXTURES } from '../../../../test/fixtures/biDashboardFixtures';
import { useBiDashboard } from '../../hooks/useBiDashboard';
import { fetchBiDashboard } from '../../services/api';
import type { BiCompanySummary } from '../../types';

const {
  createBiMaterializationMock,
  refreshBiDashboardMock,
  streamBiMaterializationJobMock,
  streamBiQuestionJobMock,
} = vi.hoisted(() => ({
  createBiMaterializationMock: vi.fn(),
  refreshBiDashboardMock: vi.fn(),
  streamBiMaterializationJobMock: vi.fn(),
  streamBiQuestionJobMock: vi.fn(),
}));

vi.mock('../../services/api', async (importOriginal) => ({
  ...await importOriginal<typeof import('../../services/api')>(),
  createBiMaterialization: createBiMaterializationMock,
  fetchBiDashboard: vi.fn(),
  refreshBiDashboard: refreshBiDashboardMock,
  streamBiMaterializationJob: streamBiMaterializationJobMock,
  streamBiQuestionJob: streamBiQuestionJobMock,
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
const CURRENT_COMPANY: BiCompanySummary = {
  ...CURRENT_DASHBOARD.company,
  source: CURRENT_DASHBOARD.source,
  currentSnapshotId: CURRENT_DASHBOARD.snapshot.snapshotId,
  snapshotStatus: CURRENT_DASHBOARD.snapshot.status,
  refreshStatus: CURRENT_DASHBOARD.refresh.status,
  updatedAt: CURRENT_DASHBOARD.snapshot.generatedAt,
};

function questionProgress(completedQuestions: number, failedQuestions = 0) {
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
    createBiMaterializationMock.mockReset();
    vi.mocked(fetchBiDashboard).mockReset();
    refreshBiDashboardMock.mockReset();
    streamBiMaterializationJobMock.mockReset();
    streamBiQuestionJobMock.mockReset();
  });

  it('materializes a DB catalog company once when it has no published snapshot', async () => {
    const sourceCompany: BiCompanySummary = {
      ...CURRENT_COMPANY,
      currentSnapshotId: null,
      snapshotStatus: null,
      refreshStatus: 'idle',
      updatedAt: null,
    };
    const readyJob = {
      jobId: 'job-initial',
      companyId: sourceCompany.companyId,
      workbookHash: sourceCompany.source?.workbookHash ?? 'a'.repeat(64),
      status: 'partial' as const,
      completedRequests: 9,
      totalRequests: 10,
      publishedSnapshotId: CURRENT_DASHBOARD.snapshot.snapshotId,
      errorCode: null,
      message: null,
      startedAt: '2026-08-20T10:00:00Z',
      updatedAt: '2026-08-20T10:01:00Z',
    };
    createBiMaterializationMock.mockResolvedValue({
      jobId: readyJob.jobId,
      status: 'queued',
      publishedSnapshotId: null,
    });
    streamBiMaterializationJobMock.mockImplementation(async (_jobId, onUpdate) => {
      onUpdate(readyJob);
      return readyJob;
    });
    vi.mocked(fetchBiDashboard).mockResolvedValue({
      kind: 'snapshot',
      dashboard: CURRENT_DASHBOARD,
    });

    const { result } = renderHook(() => useBiDashboard(sourceCompany));

    await waitFor(() => expect(result.current.state.status).toBe('ready'));
    expect(createBiMaterializationMock).toHaveBeenCalledWith({
      companyId: sourceCompany.companyId,
      displayName: sourceCompany.displayName,
      source: sourceCompany.source,
    }, expect.any(AbortSignal));
    expect(streamBiMaterializationJobMock).toHaveBeenCalledWith(
      readyJob.jobId,
      expect.any(Function),
      expect.any(AbortSignal),
    );
  });

  it('keeps the current snapshot while a refresh is processing', async () => {
    vi.mocked(fetchBiDashboard).mockResolvedValue({
      kind: 'snapshot',
      dashboard: CURRENT_DASHBOARD,
    });
    refreshBiDashboardMock.mockResolvedValue(questionProgress(0));
    streamBiQuestionJobMock.mockImplementation(async (_jobId, onUpdate) => {
      onUpdate(questionProgress(4));
      return new Promise(() => undefined);
    });
    const { result } = renderHook(() => useBiDashboard(CURRENT_COMPANY));
    await waitFor(() => expect(result.current.state.status).toBe('ready'));

    act(() => { void result.current.refresh(); });

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
    vi.mocked(fetchBiDashboard)
      .mockResolvedValueOnce({ kind: 'snapshot', dashboard: CURRENT_DASHBOARD })
      .mockResolvedValueOnce({ kind: 'snapshot', dashboard: NEXT_DASHBOARD });
    refreshBiDashboardMock.mockResolvedValue(questionProgress(0));
    streamBiQuestionJobMock.mockImplementation(async (_jobId, onUpdate) => {
      const completed = questionProgress(10);
      onUpdate(completed);
      return completed;
    });
    const { result } = renderHook(() => useBiDashboard(CURRENT_COMPANY));
    await waitFor(() => expect(result.current.state.status).toBe('ready'));

    await act(async () => result.current.refresh());

    await waitFor(() => {
      expect(result.current.state.status).toBe('ready');
      if (result.current.state.status !== 'ready') return;
      expect(result.current.state.dashboard.snapshot.snapshotId).toBe('fixture-ready-002');
    });
  });

  it('keeps the current snapshot and reports a nonblocking refresh failure', async () => {
    vi.mocked(fetchBiDashboard).mockResolvedValue({
      kind: 'snapshot',
      dashboard: CURRENT_DASHBOARD,
    });
    refreshBiDashboardMock.mockResolvedValue(questionProgress(0));
    streamBiQuestionJobMock.mockRejectedValue(new Error('queue failed'));
    const { result } = renderHook(() => useBiDashboard(CURRENT_COMPANY));
    await waitFor(() => expect(result.current.state.status).toBe('ready'));

    await act(async () => result.current.refresh());

    await waitFor(() => {
      expect(result.current.state.status).toBe('ready');
      if (result.current.state.status !== 'ready') return;
      expect(result.current.state.dashboard.snapshot.snapshotId).toBe('fixture-ready-001');
      expect(result.current.state.dashboard.refresh.status).toBe('failed');
    });
  });
});
