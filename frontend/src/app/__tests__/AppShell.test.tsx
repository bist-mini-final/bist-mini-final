import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AppShell } from '../AppShell';
import { APP_ROUTES } from '../routes';
import { SidebarContextPortal } from '../SidebarContextPortal';

describe('AppShell sidebar navigation', () => {
  it('places jobs with the bottom system routes', () => {
    render(
      <AppShell pathname="/">
        <div>content</div>
      </AppShell>,
    );

    const primaryNavigation = screen.getByRole('navigation', { name: '주요 메뉴' });
    const systemNavigation = screen.getByRole('navigation', { name: '시스템 및 설정' });

    expect(within(primaryNavigation).queryByRole('link', { name: '작업 관제' }))
      .not.toBeInTheDocument();
    expect(within(systemNavigation).getAllByRole('link').map((link) => link.textContent))
      .toEqual(['작업 관제', '설정', 'API 문서']);
  });

  it('wraps document routes in the shared page viewport', () => {
    const dashboardRoute = APP_ROUTES.find((route) => route.path === '/dashboard');

    render(
      <AppShell activeRoute={dashboardRoute} pathname="/dashboard">
        <div data-testid="dashboard-content">content</div>
      </AppShell>,
    );

    expect(screen.getByTestId('dashboard-content').parentElement)
      .toHaveClass('product-page__viewport');
  });

  it('keeps the playground canvas full bleed', () => {
    const playgroundRoute = APP_ROUTES.find((route) => route.path === '/playground');

    render(
      <AppShell activeRoute={playgroundRoute} pathname="/playground">
        <div data-testid="playground-content">canvas</div>
      </AppShell>,
    );

    expect(screen.getByTestId('playground-content').parentElement)
      .toHaveClass('product-page', 'product-page--playground');
    expect(screen.getByTestId('playground-content').parentElement)
      .not.toHaveClass('product-page__viewport');
  });

  it('shows chatbot-owned controls below the primary navigation', () => {
    const chatbotRoute = APP_ROUTES.find((route) => route.path === '/chatbot');

    render(
      <AppShell activeRoute={chatbotRoute} pathname="/chatbot">
        <SidebarContextPortal>
          <button type="button">새 대화</button>
        </SidebarContextPortal>
      </AppShell>,
    );

    const sidebarContext = screen.getByLabelText('챗봇 대화 탐색');
    expect(sidebarContext.previousElementSibling)
      .toHaveClass('product-sidebar__context-divider');
    expect(within(sidebarContext).getByRole('button', { name: '새 대화' }))
      .toBeInTheDocument();
  });

  it('preloads a lazy route when navigation intent is detected', () => {
    const chatbotRoute = APP_ROUTES.find((route) => route.path === '/chatbot');
    expect(chatbotRoute).toBeDefined();
    if (!chatbotRoute) return;

    const originalPreload = chatbotRoute.preload;
    const preload = vi.fn().mockResolvedValue(undefined);
    chatbotRoute.preload = preload;

    try {
      render(
        <AppShell pathname="/">
          <div>content</div>
        </AppShell>,
      );

      fireEvent.mouseEnter(screen.getByRole('link', { name: 'AI 챗봇' }));
      expect(preload).toHaveBeenCalledOnce();
    } finally {
      chatbotRoute.preload = originalPreload;
    }
  });
});
