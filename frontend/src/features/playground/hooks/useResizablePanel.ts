import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';

const STORAGE_KEY = 'rag-flow:module-palette-width';
export const MODULE_PANEL_MIN_WIDTH = 272;
export const MODULE_PANEL_MAX_WIDTH = 520;
const DEFAULT_WIDTH = 348;

function clampWidth(width: number) {
  return Math.min(MODULE_PANEL_MAX_WIDTH, Math.max(MODULE_PANEL_MIN_WIDTH, width));
}

function storedWidth() {
  const value = Number(window.localStorage.getItem(STORAGE_KEY));
  return Number.isFinite(value) && value > 0 ? clampWidth(value) : DEFAULT_WIDTH;
}

export function useResizablePanel() {
  const [width, setWidth] = useState(storedWidth);
  const widthRef = useRef(width);
  const cleanupRef = useRef<(() => void) | null>(null);

  useEffect(() => () => cleanupRef.current?.(), []);

  const resizeBy = useCallback((delta: number) => {
    const next = clampWidth(widthRef.current + delta);
    widthRef.current = next;
    setWidth(next);
    window.localStorage.setItem(STORAGE_KEY, String(next));
  }, []);

  const startResize = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    cleanupRef.current?.();
    const startX = event.clientX;
    const startWidth = widthRef.current;
    document.body.classList.add('is-resizing-module-palette');

    const onPointerMove = (moveEvent: PointerEvent) => {
      const next = clampWidth(startWidth + moveEvent.clientX - startX);
      widthRef.current = next;
      setWidth(next);
    };
    const cleanup = () => {
      document.body.classList.remove('is-resizing-module-palette');
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', cleanup);
      window.removeEventListener('pointercancel', cleanup);
      window.localStorage.setItem(STORAGE_KEY, String(widthRef.current));
      cleanupRef.current = null;
    };

    cleanupRef.current = cleanup;
    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', cleanup);
    window.addEventListener('pointercancel', cleanup);
  }, []);

  return { width, startResize, resizeBy };
}
