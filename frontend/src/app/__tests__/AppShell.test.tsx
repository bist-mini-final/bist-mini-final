import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ChatWorkspaceProvider } from '../../features/chatbot/ChatWorkspaceProvider';
import { AppShell } from '../AppShell';
import { APP_ROUTES } from '../routes';

vi.mock('../../features/chatbot/chatApi', () => ({
  chatApi: {
    list: vi.fn().mockResolvedValue({ sessions: [] }),
    suggestions: vi.fn().mockResolvedValue({ questions: [] }),
  },
}));

function renderShell(shell: React.ReactElement) {
  return render(<ChatWorkspaceProvider>{shell}</ChatWorkspaceProvider>);
}

describe('AppShell sidebar navigation', () => {
  it('places jobs with the bottom system routes', () => {
    renderShell(
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

    renderShell(
      <AppShell activeRoute={dashboardRoute} pathname="/dashboard">
        <div data-testid="dashboard-content">content</div>
      </AppShell>,
    );

    expect(screen.getByTestId('dashboard-content').parentElement)
      .toHaveClass('product-page__viewport');
  });

  it('keeps the playground canvas full bleed', () => {
    const playgroundRoute = APP_ROUTES.find((route) => route.path === '/playground');

    renderShell(
      <AppShell activeRoute={playgroundRoute} pathname="/playground">
        <div data-testid="playground-content">canvas</div>
      </AppShell>,
    );

    expect(screen.getByTestId('playground-content').parentElement)
      .toHaveClass('product-page', 'product-page--playground');
    expect(screen.getByTestId('playground-content').parentElement)
      .not.toHaveClass('product-page__viewport');
  });

  it('places the global new-chat action above features and history below them', () => {
    const chatbotRoute = APP_ROUTES.find((route) => route.path === '/chatbot');

    renderShell(
      <AppShell activeRoute={chatbotRoute} pathname="/chatbot">
        <div>chat</div>
      </AppShell>,
    );

    const newChat = screen.getByRole('button', { name: '새 채팅' });
    const primaryNavigation = screen.getByRole('navigation', { name: '주요 메뉴' });
    const sidebarContext = screen.getByLabelText('챗봇 대화 탐색');
    expect(newChat.nextElementSibling).toHaveClass('product-sidebar__primary-divider');
    expect(primaryNavigation.nextElementSibling)
      .toHaveClass('product-sidebar__context-divider');
    expect(sidebarContext.previousElementSibling)
      .toHaveClass('product-sidebar__context-divider');
    expect(within(sidebarContext).getByText('대화 이력')).toBeInTheDocument();
  });

  it('keeps conversation history available outside the chat route', () => {
    const dashboardRoute = APP_ROUTES.find((route) => route.path === '/dashboard');

    renderShell(
      <AppShell activeRoute={dashboardRoute} pathname="/dashboard">
        <div>dashboard</div>
      </AppShell>,
    );

    expect(screen.getByLabelText('챗봇 대화 탐색')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '새 채팅' })).toBeInTheDocument();
  });

  it('provides a mobile top bar and an accessible menu drawer without bottom navigation', () => {
    const dashboardRoute = APP_ROUTES.find((route) => route.path === '/dashboard');

    renderShell(
      <AppShell activeRoute={dashboardRoute} pathname="/dashboard">
        <div>dashboard</div>
      </AppShell>,
    );

    expect(screen.getByRole('banner')).toHaveTextContent('Excel RAG');
    expect(screen.getByRole('banner')).toHaveTextContent('BI 대시보드');
    expect(screen.queryByRole('navigation', { name: '모바일 주요 메뉴' }))
      .not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '전체 메뉴 열기' }));
    const drawer = screen.getByRole('dialog', { name: '서비스 내비게이션' });
    expect(drawer).toHaveClass('product-sidebar--open');
    expect(within(drawer).getByRole('button', { name: '메뉴 닫기' })).toBeInTheDocument();
  });

  it('preloads a lazy route when navigation intent is detected', () => {
    const playgroundRoute = APP_ROUTES.find((route) => route.path === '/playground');
    expect(playgroundRoute).toBeDefined();
    if (!playgroundRoute) return;

    const originalPreload = playgroundRoute.preload;
    const preload = vi.fn().mockResolvedValue(undefined);
    playgroundRoute.preload = preload;

    try {
      renderShell(
        <AppShell pathname="/">
          <div>content</div>
        </AppShell>,
      );

      fireEvent.mouseEnter(screen.getByRole('link', { name: '플레이그라운드' }));
      expect(preload).toHaveBeenCalledOnce();
    } finally {
      playgroundRoute.preload = originalPreload;
    }
  });
});
