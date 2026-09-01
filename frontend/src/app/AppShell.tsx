import { useEffect, useRef, useState, type ReactNode } from 'react';
import {
  Bell,
  LogOut,
  MessageSquarePlus,
  PanelLeftClose,
  PanelLeftOpen,
  X,
} from 'lucide-react';
import clsx from 'clsx';
import { ChatSessionSidebar } from '../features/chatbot/ChatSessionSidebar';
import { useAuth } from '../features/auth/AuthProvider';
import { useChatWorkspace } from '../features/chatbot/ChatWorkspaceProvider';
import { CellEvidenceProvider } from '../shared/evidence/CellEvidenceProvider';
import { ConfirmDialog, IconButton, PromptDialog } from '../shared/ui';
import { useFocusTrap } from '../shared/ui/useFocusTrap';
import type { AppRoute } from './routes';
import { APP_ROUTES } from './routes';
import { AppLink, navigateTo } from './router';
import { MobileAppBar } from './MobileAppBar';

interface AppShellProps {
  activeRoute?: AppRoute;
  pathname: string;
  children: ReactNode;
}

const SIDEBAR_STORAGE_KEY = 'rag-flow:sidebar-collapsed';
const SYSTEM_ROUTE_PATHS = new Set(['/jobs', '/settings']);
const TOP_ACTION_ROUTE_PATHS = new Set(['/chatbot']);

function preloadRoute(route: AppRoute): void {
  if (!route.preload) return;
  void route.preload().catch(() => undefined);
}

export function AppShell({ activeRoute, pathname, children }: AppShellProps) {
  const chat = useChatWorkspace();
  const auth = useAuth();
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);
  const [isNotificationOpen, setIsNotificationOpen] = useState(false);
  const mobileTriggerRef = useRef<HTMLButtonElement>(null);
  const sidebarRef = useRef<HTMLElement>(null);
  const mainRef = useRef<HTMLElement>(null);
  const previousPathRef = useRef(pathname);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(() => {
    if (typeof window === 'undefined') return false;
    try {
      return localStorage.getItem(SIDEBAR_STORAGE_KEY) === 'true';
    } catch {
      return false;
    }
  });

  const toggleSidebar = () => {
    setIsNotificationOpen(false);
    setIsSidebarCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(SIDEBAR_STORAGE_KEY, String(next));
      } catch {
        // Ignore storage errors
      }
      return next;
    });
  };

  const isFullBleedPage = activeRoute?.path === '/playground';
  const isWorkspacePage = activeRoute?.path === '/chatbot';

  const startNewChat = () => {
    chat.newSession();
    setIsMobileNavOpen(false);
    navigateTo('/chatbot');
  };

  const selectChatSession = (sessionId: string) => {
    setIsMobileNavOpen(false);
    navigateTo('/chatbot');
    void chat.selectSession(sessionId);
  };

  useEffect(() => {
    setIsMobileNavOpen(false);
    setIsNotificationOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!isNotificationOpen) return undefined;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setIsNotificationOpen(false);
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [isNotificationOpen]);

  useEffect(() => {
    if (previousPathRef.current === pathname) return;
    previousPathRef.current = pathname;
    const frame = window.requestAnimationFrame(() => {
      if (mainRef.current) {
        mainRef.current.scrollTop = 0;
        mainRef.current.focus();
      }
    });
    return () => window.cancelAnimationFrame(frame);
  }, [pathname]);

  useFocusTrap({
    active: isMobileNavOpen,
    containerRef: sidebarRef,
    restoreFocusRef: mobileTriggerRef,
    initialFocusSelector: '.product-brand__link',
    onEscape: () => setIsMobileNavOpen(false),
  });

  return (
    <CellEvidenceProvider>
      <div className="product-shell">
        <MobileAppBar
          activeRoute={activeRoute}
          menuButtonRef={mobileTriggerRef}
          notificationOpen={isNotificationOpen}
          onOpenMenu={() => {
            setIsNotificationOpen(false);
            setIsMobileNavOpen(true);
          }}
          onToggleNotification={() => setIsNotificationOpen((open) => !open)}
        />

        <aside
          ref={sidebarRef}
          id="product-sidebar"
          className={clsx(
            'product-sidebar',
            isSidebarCollapsed && 'product-sidebar--collapsed',
            isMobileNavOpen && 'product-sidebar--open',
          )}
          aria-label="서비스 내비게이션"
          role={isMobileNavOpen ? 'dialog' : undefined}
          aria-modal={isMobileNavOpen || undefined}
          tabIndex={isMobileNavOpen ? -1 : undefined}
        >
        <div className="product-brand">
          <AppLink to="/chatbot" className="product-brand__link" title="Excel RAG">
            <span className="product-brand__copy">
              <strong>Excel RAG</strong>
            </span>
          </AppLink>
          <div className="product-brand__actions">
            <IconButton
              className="product-brand__notification"
              variant="ghost"
              size="sm"
              onClick={() => setIsNotificationOpen((open) => !open)}
              aria-label="알림"
              aria-expanded={isNotificationOpen}
              title="알림"
            >
              <Bell size={16} aria-hidden="true" />
            </IconButton>
            <IconButton
              className="product-sidebar__collapse-btn"
              variant="ghost"
              size="sm"
              onClick={toggleSidebar}
              aria-label={isSidebarCollapsed ? '사이드바 펼치기' : '사이드바 접기'}
              title={isSidebarCollapsed ? '사이드바 펼치기' : '사이드바 접기'}
            >
              {isSidebarCollapsed
                ? <PanelLeftOpen size={16} aria-hidden="true" />
                : <PanelLeftClose size={16} aria-hidden="true" />}
            </IconButton>
            <IconButton
              className="product-sidebar__close"
              variant="ghost"
              size="sm"
              onClick={() => setIsMobileNavOpen(false)}
              aria-label="메뉴 닫기"
            >
              <X size={17} aria-hidden="true" />
            </IconButton>
          </div>
          {isNotificationOpen && (
            <div className="product-brand__notification-popover" role="status">
              <strong>알림</strong>
              <span>새 알림이 없습니다.</span>
            </div>
          )}
        </div>

        <button
          type="button"
          className={clsx(
            'product-nav__item',
            'product-nav__item--new-chat',
            activeRoute?.path === '/chatbot' && 'is-active',
          )}
          onClick={startNewChat}
          disabled={chat.isRunning}
          aria-current={activeRoute?.path === '/chatbot' ? 'page' : undefined}
          title="새 채팅"
        >
          <MessageSquarePlus size={18} strokeWidth={1.9} aria-hidden="true" />
          <span className="product-nav__label">새 채팅</span>
        </button>

        <div className="product-sidebar__divider product-sidebar__primary-divider" />

        <nav className="product-nav" aria-label="주요 메뉴">
          {APP_ROUTES.filter((route) => (
            !SYSTEM_ROUTE_PATHS.has(route.path) && !TOP_ACTION_ROUTE_PATHS.has(route.path)
          )).map((route) => {
            const Icon = route.icon;
            const isActive = route.path === activeRoute?.path;
            return (
              <AppLink
                key={route.path}
                to={route.path}
                className={clsx('product-nav__item', isActive && 'is-active')}
                aria-current={isActive ? 'page' : undefined}
                title={route.label}
                aria-label={route.label}
                onMouseEnter={() => preloadRoute(route)}
                onFocus={() => preloadRoute(route)}
              >
                <Icon size={18} strokeWidth={1.9} aria-hidden="true" />
                <span className="product-nav__label">{route.label}</span>
                {route.status === 'planned' && (
                  <small className="product-nav__badge">예정</small>
                )}
              </AppLink>
            );
          })}
        </nav>

        <div className="product-sidebar__divider product-sidebar__context-divider" />
        <div className="product-sidebar__context" aria-label="챗봇 대화 탐색">
          <ChatSessionSidebar
            sessions={chat.sessions}
            activeSessionId={chat.active?.id}
            disabled={chat.isRunning}
            onSelectSession={selectChatSession}
            onRenameSession={chat.requestRename}
            onDeleteSession={chat.requestDelete}
          />
        </div>

        <div className="product-sidebar__spacer" />

        <div className="product-sidebar__divider" />

        <nav className="product-nav product-nav--bottom" aria-label="시스템 및 설정">
          {APP_ROUTES.filter((route) => SYSTEM_ROUTE_PATHS.has(route.path)).map((route) => {
            const Icon = route.icon;
            const isActive = activeRoute?.path === route.path;
            return (
              <AppLink
                key={route.path}
                to={route.path}
                className={clsx('product-nav__item', isActive && 'is-active')}
                aria-current={isActive ? 'page' : undefined}
                title={route.label}
                aria-label={route.label}
                onMouseEnter={() => preloadRoute(route)}
                onFocus={() => preloadRoute(route)}
              >
                <Icon size={18} strokeWidth={1.9} aria-hidden="true" />
                <span className="product-nav__label">{route.label}</span>
              </AppLink>
            );
          })}

          {auth.enabled && (
            <button
              type="button"
              className="product-nav__item"
              onClick={() => { void auth.logout(); }}
              title="로그아웃"
            >
              <LogOut size={18} strokeWidth={1.9} aria-hidden="true" />
              <span className="product-nav__label">로그아웃</span>
            </button>
          )}

        </nav>
        </aside>

        {isMobileNavOpen && (
          <button
            className="product-sidebar-backdrop"
            type="button"
            onClick={() => setIsMobileNavOpen(false)}
            aria-label="메뉴 닫기"
          />
        )}

        <main
          ref={mainRef}
          tabIndex={-1}
          className={clsx(
            'product-page',
            isFullBleedPage && 'product-page--playground'
          )}
        >
          {isFullBleedPage ? children : (
            <div
              className={clsx(
                'product-page__viewport',
                isWorkspacePage && 'product-page__viewport--workspace',
              )}
            >
              {children}
            </div>
          )}
        </main>

        <ConfirmDialog
          open={chat.dialog?.type === 'delete'}
          tone="danger"
          title="대화를 삭제하시겠습니까?"
          description="대화와 포함된 모든 메시지가 영구 삭제됩니다."
          detail={chat.dialog?.type === 'delete' ? chat.dialog.session.title : undefined}
          confirmLabel="대화 삭제"
          busy={chat.isDialogBusy}
          error={chat.dialogError}
          onClose={chat.closeDialog}
          onConfirm={() => { void chat.deleteSession(); }}
        />
        <PromptDialog
          open={chat.dialog?.type === 'rename'}
          title="대화 이름 변경"
          description="사이드바에서 구분하기 쉬운 이름을 입력하세요."
          label="대화 이름"
          initialValue={chat.dialog?.type === 'rename' ? chat.dialog.session.title : ''}
          confirmLabel="이름 변경"
          busy={chat.isDialogBusy}
          error={chat.dialogError}
          onClose={chat.closeDialog}
          onConfirm={(title) => { void chat.renameSession(title); }}
        />
      </div>
    </CellEvidenceProvider>
  );
}
