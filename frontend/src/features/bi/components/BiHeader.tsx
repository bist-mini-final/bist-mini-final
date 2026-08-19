import { Building2, CalendarRange, CheckCircle2, CircleAlert, Clock3, FlaskConical } from 'lucide-react';
import type { BiDashboardSnapshot, PeriodRange } from '../types';

interface BiHeaderProps {
  readonly dashboard: BiDashboardSnapshot;
  readonly periodLabel: PeriodRange;
}

export function BiHeader({ dashboard, periodLabel }: BiHeaderProps) {
  const isPartial = dashboard.snapshot.status === 'partial';
  const generatedAt = dashboard.snapshot.generatedAt.slice(0, 16).replace('T', ' ').split('-').join('.');

  return (
    <header className="bi-header">
      <div className="bi-header__title-group">
        <span className="bi-header__eyebrow">COMPANY DASHBOARD</span>
        <h1 id="bi-page-title">기업 Dashboard</h1>
        <p>기업의 핵심 재무 흐름을 쉬운 구조로 살펴보는 <span>작업 공간입니다.</span></p>
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
            <dt><Building2 size={15} aria-hidden="true" />선택 기업</dt>
            <dd title={dashboard.company.displayName}>{dashboard.company.displayName}</dd>
          </div>
          <div>
            <dt><CalendarRange size={15} aria-hidden="true" />기준 기간</dt>
            <dd>{periodLabel}</dd>
          </div>
          <div>
            <dt><Clock3 size={15} aria-hidden="true" />업데이트</dt>
            <dd title={generatedAt}>{generatedAt}</dd>
          </div>
        </dl>
        <span className="bi-fixture-note">
          <FlaskConical size={14} aria-hidden="true" />현재 화면은 디자인 검증용 fixture 데이터입니다.
        </span>
      </div>
    </header>
  );
}
