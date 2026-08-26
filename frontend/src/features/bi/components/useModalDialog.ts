import { useEffect, useRef } from 'react';

export function useModalDialog() {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const activeElement = document.activeElement;
  const returnFocusRef = useRef(
    activeElement instanceof HTMLElement && activeElement !== document.body
      ? activeElement
      : null,
  );

  useEffect(() => {
    if (dialogRef.current && !dialogRef.current.open) dialogRef.current.showModal();

    return () => {
      const returnFocusElement = returnFocusRef.current;
      if (returnFocusElement) queueMicrotask(() => returnFocusElement.focus());
    };
  }, []);

  return dialogRef;
}
