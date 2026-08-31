import { useSyncExternalStore } from 'react';

function getMediaQueryList(query: string): MediaQueryList | null {
  return typeof window === 'undefined' || typeof window.matchMedia !== 'function'
    ? null
    : window.matchMedia(query);
}

/**
 * Subscribes React to a viewport query without keeping a second, drifting copy
 * of responsive state in individual feature components.
 */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const mediaQuery = getMediaQueryList(query);
      if (!mediaQuery) return () => undefined;
      mediaQuery.addEventListener('change', onChange);
      return () => mediaQuery.removeEventListener('change', onChange);
    },
    () => getMediaQueryList(query)?.matches ?? false,
    () => false,
  );
}

