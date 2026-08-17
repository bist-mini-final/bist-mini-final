import { useEffect, useState, type ReactNode } from 'react';
import {
  ArrowUpRight,
  BookOpen,
  ChevronDown,
  Menu,
  Sparkles,
  Workflow,
  X,
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

export function AppShell({ activeRoute, pathname, children }: AppShellProps) {
  const [isNavigationOpen, setIsNavigationOpen] = useState(false);

  useEffect(() => {
    setIsNavigationOpen(false);
  }, [pathname]);

  return (
    <div className="product-shell">
      <aside
        className={clsx('product-sidebar', isNavigationOpen && 'product-sidebar--open')}
        aria-label="서비스 내비게이션"
      >
        <div className="product-brand">
          <span className="product-brand__mark" aria-hidden="true">
            <Workflow size={18} strokeWidth={2.2} />
          </span>
          <span className="product-brand__copy">
            <strong>RAG Flow</strong>
            <small>AI Workspace</small>
          </span>
          <button
            className="product-sidebar__close"
            type="button"
            onClick={() => setIsNavigationOpen(false)}
            aria-label="메뉴 닫기"
          >
            <X size={18} />
          </button>
        </div>

        <button className="workspace-switcher" type="button">
          <span className="workspace-switcher__avatar">B</span>
          <span>
            <strong>BIST Workspace</strong>
            <small>Team project</small>
          </span>
          <ChevronDown size={15} aria-hidden="true" />
        </button>

        <nav className="product-nav" aria-label="주요 메뉴">
          <span className="product-nav__caption">WORKSPACE</span>
          {APP_ROUTES.map((route) => {
            const Icon = route.icon;
            const isActive = route.path === pathname;
            return (
              <AppLink
                key={route.path}
                to={route.path}
                className={clsx('product-nav__item', isActive && 'is-active')}
                aria-current={isActive ? 'page' : undefined}
              >
                <Icon size={18} strokeWidth={1.9} aria-hidden="true" />
                <span>{route.label}</span>
                {route.status === 'planned' && (
                  <small className="product-nav__badge">예정</small>
                )}
              </AppLink>
            );
          })}
        </nav>

        <div className="product-sidebar__spacer" />

        <div className="product-sidebar__guide">
          <Sparkles size={17} aria-hidden="true" />
          <div>
            <strong>모듈 중심 개발</strong>
            <p>독립 DTO를 연결해 워크플로를 구성하세요.</p>
          </div>
        </div>

        <a className="product-sidebar__docs" href="/redoc" target="_blank" rel="noreferrer">
          <BookOpen size={17} aria-hidden="true" />
          <span>API 문서</span>
          <ArrowUpRight size={14} aria-hidden="true" />
        </a>
      </aside>

      {isNavigationOpen && (
        <button
          className="product-sidebar-backdrop"
          type="button"
          onClick={() => setIsNavigationOpen(false)}
          aria-label="메뉴 닫기"
        />
      )}

      <section className="product-content">
        <header className="product-topbar">
          <button
            className="product-topbar__menu"
            type="button"
            onClick={() => setIsNavigationOpen(true)}
            aria-label="메뉴 열기"
          >
            <Menu size={19} />
          </button>
          <div className="product-breadcrumb">
            <span>BIST Workspace</span>
            <span aria-hidden="true">/</span>
            <strong>{activeRoute?.label ?? '페이지를 찾을 수 없음'}</strong>
          </div>
          <div className="product-topbar__status">
            <span aria-hidden="true" />
            API connected
          </div>
        </header>

        <main
          className={clsx(
            'product-page',
            activeRoute?.path === '/playground' && 'product-page--playground'
          )}
        >
          {children}
        </main>
      </section>
    </div>
  );
}
