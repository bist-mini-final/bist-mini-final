import {
  useCallback,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type RefObject,
} from 'react';

interface DragOrigin {
  readonly pointerId: number;
  readonly clientX: number;
  readonly clientY: number;
  readonly scrollLeft: number;
  readonly scrollTop: number;
}

const INTERACTIVE_SELECTOR = 'button, a, input, select, textarea, [data-pan-ignore="true"]';

/** Converts primary-button pointer dragging into native scrolling for large canvases. */
export function useDragPan(viewportRef: RefObject<HTMLElement>) {
  const originRef = useRef<DragOrigin | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const endDrag = useCallback((event: ReactPointerEvent<HTMLElement>) => {
    const origin = originRef.current;
    if (!origin || origin.pointerId !== event.pointerId) return;
    originRef.current = null;
    setIsDragging(false);
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }, []);

  const onPointerDown = useCallback((event: ReactPointerEvent<HTMLElement>) => {
    if (event.button !== 0) return;
    const target = event.target instanceof Element ? event.target : null;
    if (target?.closest(INTERACTIVE_SELECTOR)) return;
    const viewport = viewportRef.current;
    if (!viewport) return;
    originRef.current = {
      pointerId: event.pointerId,
      clientX: event.clientX,
      clientY: event.clientY,
      scrollLeft: viewport.scrollLeft,
      scrollTop: viewport.scrollTop,
    };
    event.currentTarget.setPointerCapture?.(event.pointerId);
    event.preventDefault();
    setIsDragging(true);
  }, [viewportRef]);

  const onPointerMove = useCallback((event: ReactPointerEvent<HTMLElement>) => {
    const origin = originRef.current;
    const viewport = viewportRef.current;
    if (!origin || !viewport || origin.pointerId !== event.pointerId) return;
    viewport.scrollLeft = origin.scrollLeft - (event.clientX - origin.clientX);
    viewport.scrollTop = origin.scrollTop - (event.clientY - origin.clientY);
  }, [viewportRef]);

  return {
    isDragging,
    dragPanProps: {
      onPointerDown,
      onPointerMove,
      onPointerUp: endDrag,
      onPointerCancel: endDrag,
      onLostPointerCapture: endDrag,
    },
  } as const;
}
