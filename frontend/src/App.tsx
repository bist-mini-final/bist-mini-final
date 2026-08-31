import { Suspense, useEffect } from 'react';
import { AppShell } from './app/AppShell';
import { findRoute } from './app/routes';
import { navigateTo, usePathname } from './app/router';
import { ChatWorkspaceProvider } from './features/chatbot/ChatWorkspaceProvider';
import { NotFoundPage } from './pages/NotFoundPage';

function AppContent() {
  const pathname = usePathname();
  const activeRoute = findRoute(pathname);
  const Page = activeRoute?.component;

  useEffect(() => {
    document.title = activeRoute
      ? `${activeRoute.label} · Excel RAG`
      : '페이지를 찾을 수 없음 · Excel RAG';
  }, [activeRoute]);

  useEffect(() => {
    if (pathname === '/') navigateTo('/chatbot', true);
  }, [pathname]);

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

function App() {
  return (
    <ChatWorkspaceProvider>
      <AppContent />
    </ChatWorkspaceProvider>
  );
}

export default App;
