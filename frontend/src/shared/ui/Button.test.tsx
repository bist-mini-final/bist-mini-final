import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  Button,
  ConfirmDialog,
  IconButton,
  PageHeader,
  PromptDialog,
  StatusBadge,
  Surface,
} from '.';

describe('shared UI controls', () => {
  it('applies a stable action variant and size contract', () => {
    render(<Button variant="primary" size="lg">저장</Button>);

    expect(screen.getByRole('button', { name: '저장' })).toHaveClass(
      'ui-button--primary',
      'ui-button--lg',
    );
  });

  it('requires an accessible name for icon-only actions', () => {
    render(<IconButton aria-label="닫기">×</IconButton>);

    expect(screen.getByRole('button', { name: '닫기' })).toHaveClass('ui-button--icon');
  });

  it('uses the shared semantic badge tones', () => {
    render(<StatusBadge tone="success">사용 가능</StatusBadge>);

    expect(screen.getByText('사용 가능')).toHaveClass('ui-badge--success');
  });

  it('renders a consistent page heading and surface contract', () => {
    render(
      <>
        <PageHeader
          eyebrow="Operations"
          title="작업 관제"
          description="실행 중인 작업을 확인합니다."
          actions={<Button>새로고침</Button>}
        />
        <Surface data-testid="surface">내용</Surface>
      </>,
    );

    expect(screen.getByRole('heading', { name: '작업 관제' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '새로고침' })).toBeInTheDocument();
    expect(screen.getByTestId('surface')).toHaveClass('ui-surface');
  });

  it('provides an accessible confirmation dialog contract', async () => {
    const onClose = vi.fn();
    const onConfirm = vi.fn();
    render(
      <ConfirmDialog
        open
        title="컬렉션을 삭제하시겠습니까?"
        description="삭제한 데이터는 복구할 수 없습니다."
        confirmLabel="삭제"
        tone="danger"
        onClose={onClose}
        onConfirm={onConfirm}
      />,
    );

    expect(screen.getByRole('dialog', { name: '컬렉션을 삭제하시겠습니까?' }))
      .toHaveAttribute('aria-modal', 'true');
    await waitFor(() => expect(screen.getByRole('button', { name: '취소' })).toHaveFocus());
    fireEvent.click(screen.getByRole('button', { name: '삭제' }));
    expect(onConfirm).toHaveBeenCalledOnce();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('focuses the prompt field and submits a trimmed value', async () => {
    const onConfirm = vi.fn();
    render(
      <PromptDialog
        open
        title="새 워크플로"
        label="워크플로 이름"
        initialValue="  표준 복사본  "
        onClose={() => undefined}
        onConfirm={onConfirm}
      />,
    );

    const input = screen.getByLabelText('워크플로 이름');
    await waitFor(() => expect(input).toHaveFocus());
    fireEvent.submit(input.closest('form')!);
    expect(onConfirm).toHaveBeenCalledWith('표준 복사본');
  });
});
