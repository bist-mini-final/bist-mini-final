import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { HomePage } from './HomePage';

describe('HomePage onboarding', () => {
  it('presents the recommended journey in order with actionable destinations', () => {
    const { container } = render(<HomePage />);
    const journey = within(container.querySelector('.home-journey') as HTMLElement);

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('재무 Excel을 올리고');
    expect(screen.getByRole('heading', { name: '처음이라면 이렇게 시작하세요' })).toBeInTheDocument();
    expect(journey.getByRole('link', { name: /데이터 소스 열기/ })).toHaveAttribute('href', '/data-sources');
    expect(journey.getByRole('link', { name: /플레이그라운드 열기/ })).toHaveAttribute('href', '/playground');
    expect(journey.getByRole('link', { name: /BI 대시보드 열기/ })).toHaveAttribute('href', '/dashboard');
    expect(journey.getByRole('link', { name: /AI 챗봇 열기/ })).toHaveAttribute('href', '/chatbot');
  });

  it('exposes all five product workspaces without hard-coded company examples', () => {
    const { container } = render(<HomePage />);

    expect(container.querySelectorAll('.home-workspace')).toHaveLength(5);
    expect(screen.getByRole('link', { name: /기업 비교 열기/ })).toHaveAttribute('href', '/company-comparison');
    expect(container).not.toHaveTextContent('IBM');
    expect(container).not.toHaveTextContent('$62,472M');
  });
});
