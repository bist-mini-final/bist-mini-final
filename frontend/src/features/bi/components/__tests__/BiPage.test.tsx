import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import { BiPage } from '../../BiPage';

describe('BiPage Component', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('renders BI dashboard header, company tabs, and default cards', () => {
    render(<BiPage />);

    expect(screen.getByText('기업 BI')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'BIST 데모 주식회사' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '그린랩스' })).toBeInTheDocument();

    // Verify default metric card titles
    expect(screen.getByText('매출 및 성장')).toBeInTheDocument();
    expect(screen.getByText('수익성')).toBeInTheDocument();
    expect(screen.getByText('현금흐름')).toBeInTheDocument();
    expect(screen.getByText('재무 안정성')).toBeInTheDocument();
    expect(screen.getByText('재무 규모')).toBeInTheDocument();
  });

  it('switches active company when clicking company tab', () => {
    render(<BiPage />);

    const greenLabsTab = screen.getByRole('tab', { name: '그린랩스' });
    fireEvent.click(greenLabsTab);

    // Tab is selected and Header metadata updates to selected company
    expect(greenLabsTab).toHaveAttribute('aria-selected', 'true');
    expect(screen.getAllByText('그린랩스').length).toBeGreaterThanOrEqual(2);
  });

  it('switches period range when clicking toolbar period buttons', () => {
    render(<BiPage />);

    const recent3Btn = screen.getByRole('button', { name: '최근 3개' });
    fireEvent.click(recent3Btn);

    expect(recent3Btn).toHaveAttribute('aria-pressed', 'true');
  });

  it('opens and closes evidence dialog', () => {
    render(<BiPage />);

    // Click on evidence button of a card
    const evidenceBtns = screen.getAllByRole('button', { name: /근거 보기/i });
    expect(evidenceBtns.length).toBeGreaterThan(0);
    fireEvent.click(evidenceBtns[0]);

    // Evidence dialog opens with card specific heading
    expect(screen.getByRole('heading', { name: /근거/i })).toBeInTheDocument();
    expect(screen.getByText('EVIDENCE')).toBeInTheDocument();

    // Close dialog
    const closeBtn = screen.getByRole('button', { name: /근거 닫기/i });
    fireEvent.click(closeBtn);
    expect(screen.queryByText('EVIDENCE')).not.toBeInTheDocument();
  });

  it('toggles layout editing mode and shows card library & reset dialogs', () => {
    render(<BiPage />);

    const editModeBtn = screen.getByRole('button', { name: /배치 편집/i });
    fireEvent.click(editModeBtn);

    // Edit controls become available
    const libraryBtn = screen.getByRole('button', { name: /카드 추가/i });
    expect(libraryBtn).toBeInTheDocument();
    fireEvent.click(libraryBtn);
    expect(screen.getByText('숨긴 카드 복구')).toBeInTheDocument();

    // Close library
    const closeLibraryBtn = screen.getByRole('button', { name: /카드 목록 닫기/i });
    fireEvent.click(closeLibraryBtn);
    expect(screen.queryByText('숨긴 카드 복구')).not.toBeInTheDocument();

    // Open reset layout dialog
    const resetBtn = screen.getByRole('button', { name: /기본 배치/i });
    fireEvent.click(resetBtn);
    expect(screen.getByText('기본 배치로 초기화할까요?')).toBeInTheDocument();

    // Cancel reset
    const cancelResetBtn = screen.getByRole('button', { name: /취소/i });
    fireEvent.click(cancelResetBtn);
    expect(screen.queryByText('기본 배치로 초기화할까요?')).not.toBeInTheDocument();
  });
});
