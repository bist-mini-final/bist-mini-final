import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { BiPage } from '../../BiPage';
import { DASHBOARD_FIXTURES } from '../../../../test/fixtures/biDashboardFixtures';
import {
  fetchBiCompanies,
  fetchBiDashboard,
  refreshBiDashboard,
  streamBiMaterializationJob,
  streamBiQuestionJob,
} from '../../services/api';

vi.mock('../../services/api', async (importOriginal) => ({
  ...await importOriginal<typeof import('../../services/api')>(),
  fetchBiCompanies: vi.fn(),
  fetchBiDashboard: vi.fn(),
  refreshBiDashboard: vi.fn(),
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
    vi.mocked(refreshBiDashboard).mockResolvedValue({
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
    fireEvent.click(evidenceButtons[0]);
    expect(screen.getByRole('heading', { name: /근거/i })).toBeInTheDocument();
    expect(screen.getByText('EVIDENCE')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /원본 시트 열기/i })).toHaveAttribute(
      'href',
      expect.stringContaining('/api/spreadsheet-artifacts/'),
    );

    fireEvent.click(screen.getByRole('button', { name: /근거 닫기/i }));
    expect(screen.queryByText('EVIDENCE')).not.toBeInTheDocument();
  });

  it('starts a refresh from the current validated snapshot source', async () => {
    // Given
    render(<BiPage />);
    const refreshButton = await screen.findByRole('button', { name: /데이터 갱신/i });

    // When
    fireEvent.click(refreshButton);

    // Then
    await waitFor(() => expect(refreshBiDashboard).toHaveBeenCalledWith(
      DASHBOARD_FIXTURES[0].company.companyId,
      expect.any(AbortSignal),
    ));
  });

  it('links chatbot questions to Playground without executing them', async () => {
    // Given
    render(<BiPage />);

    // When
    const chatbotLinks = await screen.findAllByRole('link', { name: /챗봇 질문/i });

    // Then
    expect(chatbotLinks[0]).toHaveAttribute('href', expect.stringContaining('/playground?'));
    expect(chatbotLinks[0]).toHaveAttribute('href', expect.stringContaining('file_name=bist-demo.xlsx'));
    expect(chatbotLinks[0]).toHaveAttribute('href', expect.stringContaining('metric_id=revenue'));
  });

  it('toggles layout editing mode and shows card dialogs', async () => {
    render(<BiPage />);

    fireEvent.click(await screen.findByRole('button', { name: /배치 편집/i }));
    const libraryButton = screen.getByRole('button', { name: /카드 추가/i });
    fireEvent.click(libraryButton);
    expect(screen.getByRole('heading', { name: '카드 추가' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /카드 목록 닫기/i }));
    expect(screen.queryByRole('heading', { name: '카드 추가' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /기본 배치/i }));
    expect(screen.getByText('기본 배치로 초기화할까요?')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /취소/i }));
    expect(screen.queryByText('기본 배치로 초기화할까요?')).not.toBeInTheDocument();
  });
});
