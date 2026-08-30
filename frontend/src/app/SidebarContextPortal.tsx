import { useEffect, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

export const SIDEBAR_CONTEXT_SLOT_ID = 'product-sidebar-context-slot';

interface SidebarContextPortalProps {
  children: ReactNode;
}

/** Renders route-owned controls inside the persistent application sidebar. */
export function SidebarContextPortal({ children }: SidebarContextPortalProps) {
  const [host, setHost] = useState<HTMLElement | null>(null);

  useEffect(() => {
    setHost(document.getElementById(SIDEBAR_CONTEXT_SLOT_ID));
  }, []);

  return host ? createPortal(children, host) : null;
}
