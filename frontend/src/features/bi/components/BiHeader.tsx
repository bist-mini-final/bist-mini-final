import { CheckCircle2, CircleAlert, Clock3, DatabaseZap, FileSpreadsheet, RefreshCw } from 'lucide-react';
import type { BiDashboardSnapshot } from '../types';

interface BiHeaderProps {
  readonly dashboard: BiDashboardSnapshot;
  readonly activeAction: 'refresh' | 'reset' | null;
  readonly onRefresh: () => void;
  readonly onReset: () => void;
}

const KOREA_DATE_TIME_FORMATTER = new Intl.DateTimeFormat('sv-SE', {
  timeZone: 'Asia/Seoul',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
});

function formatGeneratedAt(generatedAt: string): string {
  return KOREA_DATE_TIME_FORMATTER
    .format(new Date(generatedAt))
    .replace(/-/g, '.');
}

export function BiHeader({ dashboard, activeAction, onRefresh, onReset }: BiHeaderProps) {
  const isPartial = dashboard.snapshot.status === 'partial';
  const generatedAt = formatGeneratedAt(dashboard.snapshot.generatedAt);
  const canStartAction = activeAction === null;

  return (
    <header className="bi-header">
      <div className="bi-header__title-group">
        <h1 id="bi-page-title">
          <span className="bi-header__company-name">{dashboard.company.displayName}</span>
          <span className="bi-header__dashboard-label">Dashboard</span>
        </h1>
      </div>

      <div className="bi-header__summary" aria-label="현재 대시보드 상태">
        <span className="bi-status-pill" data-status={dashboard.snapshot.status}>
          {isPartial
            ? <CircleAlert size={15} aria-hidden="true" />
            : <CheckCircle2 size={15} aria-hidden="true" />}
          {isPartial ? '부분 완료 스냅샷' : '사용 가능한 스냅샷'}
        </span>
        <dl className="bi-header__metadata">
          <div>
            <dt><FileSpreadsheet size={15} aria-hidden="true" />선택 파일</dt>
            <dd title={dashboard.source.fileName}>{dashboard.source.fileName}</dd>
          </div>
        </dl>
        <div className="bi-header__data-actions">
          <dl className="bi-header__updated-at">
            <div>
              <dt><Clock3 size={15} aria-hidden="true" />업데이트</dt>
              <dd title={generatedAt}>{generatedAt}</dd>
            </div>
          </dl>
          <button
            className="bi-refresh-button"
            type="button"
            aria-disabled={!canStartAction}
            onClick={() => {
              if (canStartAction) onRefresh();
            }}
          >
            <RefreshCw className={activeAction === 'refresh' ? 'bi-refresh-button__spinner' : undefined} size={15} aria-hidden="true" />
            {activeAction === 'refresh' ? '대시보드 갱신 중' : '대시보드 갱신'}
          </button>
          <button
            className="bi-data-reset-button"
            type="button"
            aria-disabled={!canStartAction}
            onClick={() => {
              if (canStartAction) onReset();
            }}
          >
            <DatabaseZap className={activeAction === 'reset' ? 'bi-refresh-button__spinner' : undefined} size={15} aria-hidden="true" />
            {activeAction === 'reset' ? '데이터 재생성 중' : '데이터 초기화 및 재생성'}
          </button>
        </div>
      </div>
    </header>
  );
}
