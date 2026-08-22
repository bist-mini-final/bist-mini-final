import { CircleAlert, LoaderCircle } from 'lucide-react';

interface BiDataStateProps {
  readonly title: string;
  readonly message: string;
  readonly tone: 'loading' | 'error' | 'empty';
}

export function BiDataState({ title, message, tone }: BiDataStateProps) {
  return (
    <section className="bi-page" aria-labelledby="bi-page-title">
      <div className="bi-data-state" data-tone={tone} role={tone === 'error' ? 'alert' : 'status'}>
        {tone === 'loading'
          ? <LoaderCircle className="bi-page-notice__spinner" size={22} aria-hidden="true" />
          : <CircleAlert size={22} aria-hidden="true" />}
        <div>
          <span className="bi-header__eyebrow">COMPANY DASHBOARD</span>
          <h1 id="bi-page-title">{title}</h1>
          <p>{message}</p>
        </div>
      </div>
    </section>
  );
}
