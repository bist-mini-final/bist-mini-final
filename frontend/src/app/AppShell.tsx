import { useEffect, useRef, useState, type ReactNode } from 'react';
import {
  ArrowUpRight,
  BookOpen,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  Workflow,
} from 'lucide-react';
import clsx from 'clsx';
import { CellEvidenceProvider } from '../shared/evidence/CellEvidenceProvider';
import { Button, IconButton } from '../shared/ui';
import { useFocusTrap } from '../shared/ui/useFocusTrap';
import type { AppRoute } from './routes';
import { APP_ROUTES } from './routes';
import { AppLink } from './router';
import { SIDEBAR_CONTEXT_SLOT_ID } from './SidebarContextPortal';

interface AppShellProps {
  activeRoute?: AppRoute;
  pathname: string;
  children: ReactNode;
}

const SIDEBAR_STORAGE_KEY = 'rag-flow:sidebar-collapsed';
const SYSTEM_ROUTE_PATHS = new Set(['/jobs', '/settings']);

function preloadRoute(route: AppRoute): void {
  if (!route.preload) return;
  void route.preload().catch(() => undefined);
}

export function AppShell({ activeRoute, pathname, children }: AppShellProps) {
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);
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
  const hasSidebarContext = activeRoute?.path === '/chatbot';

  useEffect(() => {
    setIsMobileNavOpen(false);
  }, [pathname]);

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
      <div className={clsx('product-shell', isSidebarCollapsed && 'product-shell--collapsed')}>
      <IconButton
        ref={mobileTriggerRef}
        className="product-mobile-trigger"
        variant="secondary"
        type="button"
        onClick={() => setIsMobileNavOpen(true)}
        aria-label="메뉴 열기"
        aria-controls="product-sidebar"
        aria-expanded={isMobileNavOpen}
      >
        <Menu size={19} />
      </IconButton>

      <aside
        ref={sidebarRef}
        id="product-sidebar"
        className={clsx(
          'product-sidebar',
          isSidebarCollapsed && 'product-sidebar--collapsed',
          isMobileNavOpen && 'product-sidebar--open',
          hasSidebarContext && 'product-sidebar--with-context',
        )}
        aria-label="서비스 내비게이션"
        role={isMobileNavOpen ? 'dialog' : undefined}
        aria-modal={isMobileNavOpen || undefined}
        tabIndex={isMobileNavOpen ? -1 : undefined}
      >
        <div className="product-brand">
          <AppLink to="/" className="product-brand__link" title="RAG Flow 홈">
            <span className="product-brand__mark" aria-hidden="true">
              <Workflow size={18} strokeWidth={2.2} />
            </span>
            <span className="product-brand__copy">
              <strong>RAG Flow</strong>
              <small>AI Workspace</small>
            </span>
          </AppLink>
        </div>

        <div className="product-sidebar__divider" />

        <nav className="product-nav" aria-label="주요 메뉴">
          {/* <span className="product-nav__caption">WORKSPACE</span> */}
          {APP_ROUTES.filter((route) => !SYSTEM_ROUTE_PATHS.has(route.path)).map((route) => {
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

        {hasSidebarContext && (
          <>
            <div className="product-sidebar__divider product-sidebar__context-divider" />
            <div
              id={SIDEBAR_CONTEXT_SLOT_ID}
              className="product-sidebar__context"
              aria-label="챗봇 대화 탐색"
            />
          </>
        )}

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

          <a
            className="product-sidebar__docs"
            href="/redoc"
            target="_blank"
            rel="noreferrer"
            title="API 문서 (ReDoc)"
            aria-label="API 문서"
          >
            <BookOpen size={17} aria-hidden="true" />
            <span className="product-sidebar__docs-label">API 문서</span>
            <ArrowUpRight className="product-sidebar__docs-arrow" size={14} aria-hidden="true" />
          </a>

          <Button
            className="product-sidebar__toggle-footer"
            variant="ghost"
            type="button"
            onClick={toggleSidebar}
            aria-label={isSidebarCollapsed ? '사이드바 펼치기' : '사이드바 접기'}
            title={isSidebarCollapsed ? '사이드바 펼치기' : '사이드바 접기'}
          >
            {isSidebarCollapsed ? (
              <PanelLeftOpen size={17} aria-hidden="true" />
            ) : (
              <>
                <PanelLeftClose size={17} aria-hidden="true" />
                <span>사이드바 접기</span>
              </>
            )}
          </Button>
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
      </div>
    </CellEvidenceProvider>
  );
}
