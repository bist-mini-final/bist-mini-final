import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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
    vi.clearAllMocks();
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

  it('renders the selected company and opens the company selector', async () => {
    render(<BiPage />);

    expect(await screen.findByRole('heading', { name: 'BIST 데모 주식회사 Dashboard' })).toBeInTheDocument();
    expect(screen.queryByText('COMPANY DASHBOARD')).not.toBeInTheDocument();
    expect(screen.getByText('BIST 데모 주식회사', { selector: '.bi-header__company-name' })).toBeInTheDocument();
    expect(screen.getByText('Dashboard', { selector: '.bi-header__dashboard-label' })).toBeInTheDocument();
    expect(screen.getByText('선택 파일')).toBeInTheDocument();
    expect(screen.getByText(DASHBOARD_FIXTURES[0].source.fileName)).toBeInTheDocument();
    expect(screen.queryByText('선택 기업')).not.toBeInTheDocument();
    expect(screen.queryByText('기준 기간')).not.toBeInTheDocument();
    const updatedAtLabel = screen.getByText('업데이트');
    const refreshButton = screen.getByRole('button', { name: '대시보드 갱신' });
    expect(
      updatedAtLabel.compareDocumentPosition(refreshButton) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(screen.getByText('현재 기업')).toBeInTheDocument();
    expect(screen.getByText('BIST 데모 주식회사', { selector: '.bi-company-selector__current strong' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '기업 선택' })).toBeInTheDocument();
    expect(screen.queryByRole('tab')).not.toBeInTheDocument();
    expect(screen.getByText('매출 및 성장')).toBeInTheDocument();
    expect(screen.getByText('수익성')).toBeInTheDocument();
    expect(screen.getByText('현금흐름')).toBeInTheDocument();
    expect(screen.getByText('재무 안정성')).toBeInTheDocument();
    expect(screen.getByText('재무 규모')).toBeInTheDocument();
    expect(fetchBiCompanies).toHaveBeenCalledTimes(1);
  });

  it('refreshes and alphabetically sorts the company list whenever the selector opens', async () => {
    const bistCompany = companyResponse.companies[0];
    const greenLabsCompany = companyResponse.companies[1];
    if (!bistCompany || !greenLabsCompany) throw new Error('missing company fixtures');
    const addedCompany = {
      ...bistCompany,
      companyId: 'aardvark-analytics',
      displayName: 'Aardvark Analytics',
    };
    const refreshedGreenLabs = {
      ...greenLabsCompany,
      source: greenLabsCompany.source ? { ...greenLabsCompany.source } : null,
    };
    const refreshedBist = {
      ...bistCompany,
      source: bistCompany.source ? { ...bistCompany.source } : null,
    };
    const numberedCompanies = Array.from({ length: 15 }, (_, index) => ({
      ...bistCompany,
      companyId: `company-${String(index + 1).padStart(2, '0')}`,
      displayName: `Company ${String(index + 1).padStart(2, '0')}`,
    }));
    vi.mocked(fetchBiCompanies)
      .mockResolvedValueOnce({ companies: [greenLabsCompany, bistCompany] })
      .mockResolvedValueOnce({
        companies: [refreshedGreenLabs, ...numberedCompanies, addedCompany, refreshedBist],
      });

    render(<BiPage />);

    expect(await screen.findByRole('heading', { name: '그린랩스 Dashboard' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '기업 선택' }));

    const dialog = screen.getByRole('dialog', { name: '기업 선택' });
    await waitFor(() => expect(within(dialog).getAllByRole('option')).toHaveLength(18));
    const options = within(dialog).getAllByRole('option');
    expect(options.map((option) => option.textContent)).toEqual([
      'Aardvark Analytics',
      'BIST 데모 주식회사',
      ...numberedCompanies.map((company) => company.displayName),
      '그린랩스',
    ]);
    await waitFor(() => expect(options[17]).toHaveFocus());
    fireEvent.keyDown(options[17], { key: 'ArrowDown' });
    expect(options[0]).toHaveFocus();
    expect(fetchBiCompanies).toHaveBeenCalledTimes(2);
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
    const selectorTrigger = screen.getByRole('button', { name: '기업 선택' });
    selectorTrigger.focus();
    fireEvent.click(selectorTrigger);
    const greenLabsOption = await screen.findByRole('option', { name: '그린랩스' });
    fireEvent.click(greenLabsOption);

    await waitFor(() => expect(fetchBiDashboard).toHaveBeenCalledWith('green-labs', expect.any(AbortSignal)));
    expect(screen.getByRole('heading', { name: '그린랩스 Dashboard' })).toBeInTheDocument();
    expect(screen.getByText('그린랩스', { selector: '.bi-company-selector__current strong' })).toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: '기업 선택' })).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('button', { name: '기업 선택' })).toHaveFocus());
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
    fireEvent.click(screen.getByRole('button', { name: '기업 선택' }));
    fireEvent.click(await screen.findByRole('option', { name: '그린랩스' }));
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
