import type { HTMLAttributes, ReactNode } from 'react';

function classes(...values: Array<string | false | null | undefined>): string {
  return values.filter(Boolean).join(' ');
}

export interface PageHeaderProps extends Omit<HTMLAttributes<HTMLElement>, 'title'> {
  readonly eyebrow?: ReactNode;
  readonly title: ReactNode;
  readonly description?: ReactNode;
  readonly actions?: ReactNode;
}

/** Shared document-page heading with a stable title, description, and action rhythm. */
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  className,
  ...props
}: PageHeaderProps) {
  return (
    <header className={classes('ui-page-header', className)} {...props}>
      <div className="ui-page-header__copy">
        {eyebrow ? <span className="ui-page-header__eyebrow">{eyebrow}</span> : null}
        <h1>{title}</h1>
        {description ? <p>{description}</p> : null}
      </div>
      {actions ? <div className="ui-page-header__actions">{actions}</div> : null}
    </header>
  );
}

export interface SurfaceProps extends HTMLAttributes<HTMLElement> {
  readonly as?: 'article' | 'div' | 'section';
  readonly elevated?: boolean;
}

/** Product surface used for cards, panels, and document sections. */
export function Surface({
  as: Element = 'section',
  elevated = false,
  className,
  ...props
}: SurfaceProps) {
  return (
    <Element
      className={classes('ui-surface', elevated && 'ui-surface--elevated', className)}
      {...props}
    />
  );
}
