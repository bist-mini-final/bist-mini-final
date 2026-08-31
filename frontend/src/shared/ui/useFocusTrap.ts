import { useEffect, useRef, type RefObject } from 'react';

export const FOCUSABLE_SELECTOR = [
  '[data-dialog-initial-focus]',
  'button:not(:disabled)',
  'input:not(:disabled)',
  'select:not(:disabled)',
  'textarea:not(:disabled)',
  'a[href]',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

interface FocusTrapOptions {
  readonly active: boolean;
  readonly containerRef: RefObject<HTMLElement>;
  readonly onEscape?: () => void;
  readonly restoreFocusRef?: RefObject<HTMLElement>;
  readonly initialFocusSelector?: string;
}

/** Shares keyboard focus containment between dialogs and the mobile menu drawer. */
export function useFocusTrap({
  active,
  containerRef,
  onEscape,
  restoreFocusRef,
  initialFocusSelector = '[data-dialog-initial-focus]',
}: FocusTrapOptions): void {
  const onEscapeRef = useRef(onEscape);
  onEscapeRef.current = onEscape;

  useEffect(() => {
    if (!active) return undefined;
    const previousFocus = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    const returnFocusElement = restoreFocusRef?.current ?? previousFocus;
    const container = containerRef.current;
    const focusTimer = window.setTimeout(() => {
      const initialFocus = container?.querySelector<HTMLElement>(initialFocusSelector)
        ?? container?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR);
      initialFocus?.focus();
    });

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && onEscapeRef.current) {
        event.preventDefault();
        onEscapeRef.current();
        return;
      }
      if (event.key !== 'Tab' || !container) return;
      const focusable = Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR))
        .filter((element) => element.getAttribute('aria-hidden') !== 'true');
      if (focusable.length === 0) {
        event.preventDefault();
        container.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      window.clearTimeout(focusTimer);
      document.removeEventListener('keydown', handleKeyDown);
      returnFocusElement?.focus();
    };
  }, [active, containerRef, initialFocusSelector, restoreFocusRef]);
}
