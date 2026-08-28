import {
  useEffect,
  useState,
  type AnchorHTMLAttributes,
  type MouseEvent,
} from 'react';

const NAVIGATION_EVENT = 'rag-flow:navigation';

function normalizePathname(pathname: string): string {
  if (!pathname || pathname === '/') return '/';
  return pathname.replace(/\/+$/, '') || '/';
}

export function navigateTo(to: string, replace = false): void {
  const [pathname, search] = to.split('?');
  const nextPath = normalizePathname(pathname) + (search ? `?${search}` : '');
  const currentFull = normalizePathname(window.location.pathname) + (window.location.search || '');
  if (currentFull === nextPath) return;
  window.history[replace ? 'replaceState' : 'pushState']({}, '', nextPath);
  window.dispatchEvent(new Event(NAVIGATION_EVENT));
}

export function usePathname(): string {
  const [pathname, setPathname] = useState(() =>
    normalizePathname(window.location.pathname)
  );

  useEffect(() => {
    const syncPathname = () => setPathname(normalizePathname(window.location.pathname));
    window.addEventListener('popstate', syncPathname);
    window.addEventListener(NAVIGATION_EVENT, syncPathname);
    return () => {
      window.removeEventListener('popstate', syncPathname);
      window.removeEventListener(NAVIGATION_EVENT, syncPathname);
    };
  }, []);

  return pathname;
}

export interface AppLinkProps
  extends Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href'> {
  to: string;
}

export function AppLink({ to, onClick, target, ...props }: AppLinkProps) {
  const handleClick = (event: MouseEvent<HTMLAnchorElement>) => {
    onClick?.(event);
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey ||
      target === '_blank'
    ) {
      return;
    }
    event.preventDefault();
    navigateTo(to);
  };

  return <a {...props} href={to} target={target} onClick={handleClick} />;
}
