import type { HTMLAttributes, ReactNode } from 'react';

export type StatusBadgeTone = 'neutral' | 'success' | 'warning' | 'danger' | 'info';

interface StatusBadgeProps extends HTMLAttributes<HTMLSpanElement> {
  readonly tone?: StatusBadgeTone;
  readonly children: ReactNode;
}

export function StatusBadge({ tone = 'neutral', className, children, ...props }: StatusBadgeProps) {
  return (
    <span
      className={['ui-badge', `ui-badge--${tone}`, className].filter(Boolean).join(' ')}
      {...props}
    >
      {children}
    </span>
  );
}
