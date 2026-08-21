import { Check, LayoutDashboard, Pencil, Plus, RotateCcw } from 'lucide-react';

interface BiToolbarProps<Period extends string> {
  readonly periodOptions: readonly Period[];
  readonly selectedPeriod: Period;
  readonly onPeriodChange: (period: Period) => void;
  readonly isEditing: boolean;
  readonly onEditingChange: (isEditing: boolean) => void;
  readonly visibleCardCount: number;
  readonly hiddenCardCount: number;
  readonly onOpenCardLibrary: () => void;
  readonly onResetLayout: () => void;
}

export function BiToolbar<Period extends string>({
  periodOptions,
  selectedPeriod,
  onPeriodChange,
  isEditing,
  onEditingChange,
  visibleCardCount,
  hiddenCardCount,
  onOpenCardLibrary,
  onResetLayout,
}: BiToolbarProps<Period>) {
  return (
    <section className="bi-toolbar" aria-label="대시보드 도구">
      <div className="bi-toolbar__period">
        <span className="bi-toolbar__label">기간</span>
        <div className="bi-segmented-control" aria-label="표시 기간">
          {periodOptions.map((period) => (
            <button
              key={period}
              type="button"
              aria-pressed={period === selectedPeriod}
              onClick={() => onPeriodChange(period)}
            >
              {period}
            </button>
          ))}
        </div>
      </div>

      <div className="bi-toolbar__actions">
        <button
          className="bi-tool-button bi-tool-button--primary"
          type="button"
          aria-pressed={isEditing}
          onClick={() => onEditingChange(!isEditing)}
        >
          {isEditing ? <Check size={16} aria-hidden="true" /> : <Pencil size={16} aria-hidden="true" />}
          {isEditing ? '완료' : '배치 편집'}
        </button>
        <button className="bi-tool-button" type="button" onClick={onOpenCardLibrary}>
          <Plus size={16} aria-hidden="true" />카드 추가{hiddenCardCount > 0 ? ` (${hiddenCardCount})` : ''}
        </button>
        <button className="bi-tool-button" type="button" onClick={onResetLayout}>
          <RotateCcw size={16} aria-hidden="true" />기본 배치
        </button>
        <span className="bi-toolbar__layout-label">
          <LayoutDashboard size={15} aria-hidden="true" />{visibleCardCount}개 카드
        </span>
      </div>
    </section>
  );
}
