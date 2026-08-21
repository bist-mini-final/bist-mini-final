import { useEffect, useState, type ReactNode } from 'react';
import {
  ArrowUpRight,
  BookOpen,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  Workflow,
} from 'lucide-react';
import clsx from 'clsx';
import type { AppRoute } from './routes';
import { APP_ROUTES } from './routes';
import { AppLink } from './router';

interface AppShellProps {
  activeRoute?: AppRoute;
  pathname: string;
  children: ReactNode;
}

const SIDEBAR_STORAGE_KEY = 'rag-flow:sidebar-collapsed';

export function AppShell({ activeRoute, pathname, children }: AppShellProps) {
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);
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

  useEffect(() => {
    setIsMobileNavOpen(false);
  }, [pathname]);

  return (
    <div className={clsx('product-shell', isSidebarCollapsed && 'product-shell--collapsed')}>
      <button
        className="product-mobile-trigger"
        type="button"
        onClick={() => setIsMobileNavOpen(true)}
        aria-label="메뉴 열기"
      >
        <Menu size={19} />
      </button>

      <aside
        className={clsx(
          'product-sidebar',
          isSidebarCollapsed && 'product-sidebar--collapsed',
          isMobileNavOpen && 'product-sidebar--open'
        )}
        aria-label="서비스 내비게이션"
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
          {APP_ROUTES.filter((r) => r.path !== '/settings').map((route) => {
            const Icon = route.icon;
            const isActive = route.path === pathname;
            return (
              <AppLink
                key={route.path}
                to={route.path}
                className={clsx('product-nav__item', isActive && 'is-active')}
                aria-current={isActive ? 'page' : undefined}
                title={route.label}
                aria-label={route.label}
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

        <div className="product-sidebar__spacer" />

        <div className="product-sidebar__divider" />

        <div className="product-nav product-nav--bottom" aria-label="시스템 및 설정">
          {(() => {
            const settingsRoute = APP_ROUTES.find((r) => r.path === '/settings');
            if (!settingsRoute) return null;
            const Icon = settingsRoute.icon;
            const isActive = pathname === '/settings';
            return (
              <AppLink
                to="/settings"
                className={clsx('product-nav__item', isActive && 'is-active')}
                aria-current={isActive ? 'page' : undefined}
                title={settingsRoute.label}
                aria-label={settingsRoute.label}
              >
                <Icon size={18} strokeWidth={1.9} aria-hidden="true" />
                <span className="product-nav__label">{settingsRoute.label}</span>
              </AppLink>
            );
          })()}

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

          <button
            className="product-sidebar__toggle-footer"
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
          </button>
        </div>
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
        className={clsx(
          'product-page',
          activeRoute?.path === '/playground' && 'product-page--playground'
        )}
      >
        {children}
      </main>
    </div>
  );
}
