import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { BiPage } from '../../BiPage';
import { DASHBOARD_FIXTURES } from '../../../../test/fixtures/biDashboardFixtures';
import {
  fetchBiCompanies,
  fetchBiDashboard,
  refreshBiDashboard,
  resetBiDashboard,
  streamBiMaterializationJob,
  streamBiQuestionJob,
} from '../../services/api';

vi.mock('../../services/api', async (importOriginal) => ({
  ...await importOriginal<typeof import('../../services/api')>(),
  fetchBiCompanies: vi.fn(),
  fetchBiDashboard: vi.fn(),
  refreshBiDashboard: vi.fn(),
  resetBiDashboard: vi.fn(),
  streamBiMaterializationJob: vi.fn(),
  streamBiQuestionJob: vi.fn(),
}));

const companyResponse = {
  companies: DASHBOARD_FIXTURES.map((dashboard) => ({
    companyId: dashboard.company.companyId,
    displayName: dashboard.company.displayName,
    source: dashboard.source,
    currentSnapshotId: dashboard.snapshot.snapshotId,
    snapshotStatus: dashboard.snapshot.status,
    refreshStatus: dashboard.refresh.status,
    updatedAt: dashboard.snapshot.generatedAt,
  })),
};

describe('BiPage Component', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.mocked(fetchBiCompanies).mockResolvedValue(companyResponse);
    vi.mocked(refreshBiDashboard).mockResolvedValue(DASHBOARD_FIXTURES[0]);
    vi.mocked(resetBiDashboard).mockResolvedValue({
      jobId: 'question-job-refresh',
      totalQuestions: 10,
      queuedQuestions: 10,
      runningQuestions: 0,
      completedQuestions: 0,
      failedQuestions: 0,
    });
    const completedProgress = {
      jobId: 'question-job-refresh',
      totalQuestions: 10,
      queuedQuestions: 0,
      runningQuestions: 0,
      completedQuestions: 10,
      failedQuestions: 0,
    };
    vi.mocked(streamBiQuestionJob).mockImplementation(async (_jobId, onUpdate) => {
      onUpdate(completedProgress);
      return completedProgress;
    });
    vi.mocked(streamBiMaterializationJob).mockResolvedValue({
      jobId: 'job-refresh',
      companyId: DASHBOARD_FIXTURES[0].company.companyId,
      workbookHash: DASHBOARD_FIXTURES[0].source.workbookHash,
      status: 'ready',
      completedRequests: 10,
      totalRequests: 10,
      publishedSnapshotId: DASHBOARD_FIXTURES[0].snapshot.snapshotId,
      errorCode: null,
      message: null,
      startedAt: '2026-08-20T10:00:00Z',
      updatedAt: '2026-08-20T10:01:00Z',
    });
    vi.mocked(fetchBiDashboard).mockImplementation(async (companyId) => {
      const dashboard = DASHBOARD_FIXTURES.find(
        (candidate) => candidate.company.companyId === companyId,
      );
      if (!dashboard) throw new Error(`missing test dashboard: ${companyId}`);
      return { kind: 'snapshot', dashboard };
    });
  });

  it('renders API-backed company tabs and default cards', async () => {
    render(<BiPage />);

    expect(await screen.findByRole('heading', { name: 'BIST 데모 주식회사 Dashboard' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'BIST 데모 주식회사' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '그린랩스' })).toBeInTheDocument();
    expect(screen.getByText('매출 및 성장')).toBeInTheDocument();
    expect(screen.getByText('수익성')).toBeInTheDocument();
    expect(screen.getByText('현금흐름')).toBeInTheDocument();
    expect(screen.getByText('재무 안정성')).toBeInTheDocument();
    expect(screen.getByText('재무 규모')).toBeInTheDocument();
    expect(fetchBiCompanies).toHaveBeenCalledTimes(1);
  });

  it('renders the snapshot update time in Korea time', async () => {
    vi.mocked(fetchBiDashboard).mockResolvedValue({
      kind: 'snapshot',
      dashboard: {
        ...DASHBOARD_FIXTURES[0],
        snapshot: {
          ...DASHBOARD_FIXTURES[0].snapshot,
          generatedAt: '2026-08-26T00:17:29.703424Z',
        },
      },
    });

    render(<BiPage />);

    expect(await screen.findByText('2026.08.26 09:17')).toBeInTheDocument();
  });

  it('loads the selected company dashboard from the API service', async () => {
    render(<BiPage />);

    await screen.findByRole('heading', { name: 'BIST 데모 주식회사 Dashboard' });
    const greenLabsTab = screen.getByRole('tab', { name: '그린랩스' });
    fireEvent.click(greenLabsTab);

    await waitFor(() => expect(fetchBiDashboard).toHaveBeenCalledWith('green-labs', expect.any(AbortSignal)));
    expect(await screen.findByRole('tab', { name: '그린랩스' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('heading', { name: '그린랩스 Dashboard' })).toBeInTheDocument();
    expect(screen.getAllByText('그린랩스').length).toBeGreaterThanOrEqual(2);
  });

  it('keeps company switching available when the selected snapshot failed', async () => {
    vi.mocked(fetchBiCompanies).mockResolvedValue({
      companies: [
        {
          ...companyResponse.companies[0],
          currentSnapshotId: null,
          snapshotStatus: null,
          refreshStatus: 'failed',
          updatedAt: null,
        },
        companyResponse.companies[1],
      ],
    });

    render(<BiPage />);

    expect(await screen.findByRole('button', { name: '스냅샷 다시 생성' })).toBeInTheDocument();
    const greenLabsTab = screen.getByRole('tab', { name: '그린랩스' });
    fireEvent.click(greenLabsTab);
    await waitFor(() => expect(greenLabsTab).toHaveAttribute('aria-selected', 'true'));
    await waitFor(() => expect(fetchBiDashboard).toHaveBeenCalledWith(
      'green-labs',
      expect.any(AbortSignal),
    ));
  });

  it('switches period range when clicking toolbar period buttons', async () => {
    render(<BiPage />);

    const recent3Button = await screen.findByRole('button', { name: '최근 3개' });
    fireEvent.click(recent3Button);

    expect(recent3Button).toHaveAttribute('aria-pressed', 'true');
  });

  it('opens and closes evidence dialog', async () => {
    render(<BiPage />);

    const evidenceButtons = await screen.findAllByRole('button', { name: /근거 보기/i });
    evidenceButtons[0]?.focus();
    fireEvent.click(evidenceButtons[0]);
    expect(screen.getByRole('heading', { name: /근거/i })).toBeInTheDocument();
    expect(screen.getByText('EVIDENCE')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /원본 시트 열기/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /근거 닫기/i }));
    expect(screen.queryByText('EVIDENCE')).not.toBeInTheDocument();
    await waitFor(() => expect(evidenceButtons[0]).toHaveFocus());
  });

  it('starts a refresh from the current validated snapshot source', async () => {
    // Given
    render(<BiPage />);
    const refreshButton = await screen.findByRole('button', { name: /대시보드 갱신/i });

    // When
    fireEvent.click(refreshButton);

    // Then
    await waitFor(() => expect(refreshBiDashboard).toHaveBeenCalledWith(
      DASHBOARD_FIXTURES[0].company.companyId,
      expect.any(AbortSignal),
    ));
  });

  it('requires confirmation before replacing dashboard questions and answers', async () => {
    render(<BiPage />);

    fireEvent.click(await screen.findByRole('button', {
      name: '데이터 초기화 및 재생성',
    }));
    expect(screen.getByRole('heading', {
      name: 'BIST 데모 주식회사 데이터를 다시 만들까요?',
    })).toBeInTheDocument();
    expect(resetBiDashboard).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: '삭제 후 재생성' }));

    await waitFor(() => expect(resetBiDashboard).toHaveBeenCalledWith(
      DASHBOARD_FIXTURES[0].company.companyId,
      expect.any(AbortSignal),
    ));
  });

  it('returns focus to the data reset trigger when confirmation is cancelled', async () => {
    render(<BiPage />);

    const resetButton = await screen.findByRole('button', {
      name: '데이터 초기화 및 재생성',
    });
    resetButton.focus();
    fireEvent.click(resetButton);
    fireEvent.click(screen.getByRole('button', { name: '취소' }));

    await waitFor(() => expect(resetButton).toHaveFocus());
  });

  it('keeps the data reset trigger focusable while regeneration is running', async () => {
    vi.mocked(streamBiQuestionJob).mockImplementation(() => new Promise(() => undefined));
    render(<BiPage />);

    const resetButton = await screen.findByRole('button', {
      name: '데이터 초기화 및 재생성',
    });
    resetButton.focus();
    fireEvent.click(resetButton);
    fireEvent.click(screen.getByRole('button', { name: '삭제 후 재생성' }));

    const progressButton = await screen.findByRole('button', { name: '데이터 재생성 중' });
    await waitFor(() => expect(progressButton).toHaveFocus());
    expect(progressButton).toHaveAttribute('aria-disabled', 'true');
  });

  it('does not render chatbot actions in dashboard cards', async () => {
    // Given
    render(<BiPage />);

    // When
    await screen.findByRole('heading', { name: 'BIST 데모 주식회사 Dashboard' });

    // Then
    expect(screen.queryByRole('link', { name: /챗봇 질문/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /챗봇 질문/i })).not.toBeInTheDocument();
  });

  it('toggles layout editing mode and shows card dialogs', async () => {
    render(<BiPage />);

    fireEvent.click(await screen.findByRole('button', { name: /배치 편집/i }));
    const libraryButton = screen.getByRole('button', { name: /카드 추가/i });
    libraryButton.focus();
    fireEvent.click(libraryButton);
    expect(screen.getByRole('heading', { name: '카드 추가' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '추가' }));

    fireEvent.click(screen.getByRole('button', { name: /카드 목록 닫기/i }));
    expect(screen.queryByRole('heading', { name: '카드 추가' })).not.toBeInTheDocument();
    await waitFor(() => expect(libraryButton).toHaveFocus());
    expect(libraryButton).toHaveAttribute('aria-disabled', 'true');
    expect(libraryButton).toHaveAttribute('title', '숨긴 카드가 없어 추가할 수 없습니다');
    fireEvent.click(libraryButton);
    expect(screen.queryByRole('heading', { name: '카드 추가' })).not.toBeInTheDocument();

    const resetLayoutButton = screen.getByRole('button', { name: /기본 배치/i });
    resetLayoutButton.focus();
    fireEvent.click(resetLayoutButton);
    expect(screen.getByText('기본 배치로 초기화할까요?')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /취소/i }));
    expect(screen.queryByText('기본 배치로 초기화할까요?')).not.toBeInTheDocument();
    await waitFor(() => expect(resetLayoutButton).toHaveFocus());
  });
});
