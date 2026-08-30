import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Button, IconButton, StatusBadge } from '.';

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
});
