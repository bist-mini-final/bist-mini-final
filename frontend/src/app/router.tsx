import {
  useEffect,
  useState,
  type AnchorHTMLAttributes,
  type MouseEvent,
} from 'react';

const NAVIGATION_EVENT = 'rag-flow:navigation';

export interface AppLocation {
  readonly pathname: string;
  readonly search: string;
  readonly hash: string;
}

function normalizePathname(pathname: string): string {
  if (!pathname || pathname === '/') return '/';
  return pathname.replace(/\/+$/, '') || '/';
}

export function navigateTo(to: string, replace = false): void {
  const target = new URL(to, window.location.href);
  const nextPath = normalizePathname(target.pathname) + target.search + target.hash;
  const currentFull = normalizePathname(window.location.pathname)
    + window.location.search
    + window.location.hash;
  if (currentFull === nextPath) return;
  window.history[replace ? 'replaceState' : 'pushState']({}, '', nextPath);
  window.dispatchEvent(new Event(NAVIGATION_EVENT));
}

function readLocation(): AppLocation {
  return {
    pathname: normalizePathname(window.location.pathname),
    search: window.location.search,
    hash: window.location.hash,
  };
}

export function useAppLocation(): AppLocation {
  const [location, setLocation] = useState(readLocation);

  useEffect(() => {
    const syncLocation = () => setLocation(readLocation());
    window.addEventListener('popstate', syncLocation);
    window.addEventListener(NAVIGATION_EVENT, syncLocation);
    return () => {
      window.removeEventListener('popstate', syncLocation);
      window.removeEventListener(NAVIGATION_EVENT, syncLocation);
    };
  }, []);

  return location;
}

export function usePathname(): string {
  return useAppLocation().pathname;
}

export interface AppLinkProps
  extends Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href'> {
  to: string;
}

export function AppLink({ to, onClick, target, children, ...props }: AppLinkProps) {
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

  return <a {...props} href={to} target={target} onClick={handleClick}>{children}</a>;
}
