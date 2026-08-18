import { Suspense, useEffect } from 'react';
import { AppShell } from './app/AppShell';
import { findRoute } from './app/routes';
import { usePathname } from './app/router';
import { NotFoundPage } from './pages/NotFoundPage';

export function App() {
  const pathname = usePathname();
  const activeRoute = findRoute(pathname);
  const Page = activeRoute?.component;

  useEffect(() => {
    document.title = activeRoute
      ? `${activeRoute.label} · RAG Flow`
      : '페이지를 찾을 수 없음 · RAG Flow';
  }, [activeRoute]);

  return (
    <AppShell activeRoute={activeRoute} pathname={pathname}>
      {Page ? (
        <Suspense fallback={<div className="route-loading" aria-label="페이지 불러오는 중" />}>
          <Page />
        </Suspense>
      ) : (
        <NotFoundPage />
      )}
    </AppShell>
  );
}

export default App;
