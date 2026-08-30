import { useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent, ReactNode } from 'react';
import { Check, Landmark, X } from 'lucide-react';
import { Button, IconButton } from '../../../shared/ui';
import type { BiCompaniesRefreshResult } from '../hooks/useBiCompanies';
import type { BiCompanySummary } from '../types';
import { useModalDialog } from './useModalDialog';

const COMPANY_NAME_COLLATOR = new Intl.Collator(['en-US', 'ko-KR'], {
  sensitivity: 'base',
  numeric: true,
});
const COMPANY_SELECTOR_DIALOG_ID = 'bi-company-selector-dialog';

interface CompanySelectorProps {
  readonly companies: readonly BiCompanySummary[];
  readonly selectedId: string;
  readonly selectedName: string;
  readonly onSelect: (companyId: string) => void;
  readonly onRefresh: () => Promise<BiCompaniesRefreshResult>;
  readonly managementAction?: ReactNode;
}

interface CompanySelectorDialogProps extends CompanySelectorProps {
  readonly onClose: () => void;
}

function CompanySelectorDialog({
  companies,
  selectedId,
  onSelect,
  onRefresh,
  onClose,
}: CompanySelectorDialogProps) {
  const dialogRef = useModalDialog();
  const selectedOptionRef = useRef<HTMLButtonElement>(null);
  const [isRefreshing, setIsRefreshing] = useState(true);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const sortedCompanies = useMemo(() => [...companies].sort((left, right) => {
    const nameOrder = COMPANY_NAME_COLLATOR.compare(left.displayName, right.displayName);
    return nameOrder || left.companyId.localeCompare(right.companyId);
  }), [companies]);

  useEffect(() => {
    selectedOptionRef.current?.focus();
  }, [sortedCompanies]);

  useEffect(() => {
    let isActive = true;
    const refresh = async () => {
      const result = await onRefresh();
      if (!isActive) return;
      setRefreshError(result.errorMessage);
      setIsRefreshing(false);
    };
    void refresh();
    return () => { isActive = false; };
  }, [onRefresh]);

  const handleOptionKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
    const options = Array.from(
      event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="option"]') ?? [],
    );
    const currentIndex = options.indexOf(event.currentTarget);
    if (currentIndex < 0 || options.length === 0) return;

    event.preventDefault();
    let nextIndex = currentIndex;
    if (event.key === 'Home') nextIndex = 0;
    if (event.key === 'End') nextIndex = options.length - 1;
    if (event.key === 'ArrowDown') nextIndex = (currentIndex + 1) % options.length;
    if (event.key === 'ArrowUp') nextIndex = (currentIndex - 1 + options.length) % options.length;
    options[nextIndex]?.focus();
  };

  return (
    <dialog
      ref={dialogRef}
      id={COMPANY_SELECTOR_DIALOG_ID}
      className="bi-dialog bi-company-dialog"
      aria-labelledby="bi-company-dialog-title"
      onClose={onClose}
      onCancel={(event) => { event.preventDefault(); onClose(); }}
    >
      <div className="bi-dialog__header">
        <div>
          <span className="bi-dialog__eyebrow">COMPANY</span>
          <h2 id="bi-company-dialog-title">기업 선택</h2>
        </div>
        <IconButton variant="ghost" onClick={onClose} aria-label="기업 선택 닫기"><X size={18} aria-hidden="true" /></IconButton>
      </div>
      <p className="bi-company-dialog__status" aria-live="polite">
        {isRefreshing
          ? '등록된 기업 목록을 새로 확인하는 중입니다.'
          : refreshError
            ? `목록을 새로 불러오지 못해 기존 목록을 표시합니다. ${refreshError}`
            : '기업을 선택하면 해당 기업의 대시보드로 이동합니다.'}
      </p>
      <div className="bi-company-list" role="listbox" aria-label="기업 목록" aria-busy={isRefreshing}>
        {sortedCompanies.map((company) => {
          const isSelected = company.companyId === selectedId;
          return (
            <Button
              key={company.companyId}
              ref={isSelected ? selectedOptionRef : undefined}
              className="bi-company-option"
              type="button"
              role="option"
              aria-selected={isSelected}
              title={company.displayName}
              onClick={() => { onSelect(company.companyId); onClose(); }}
              onKeyDown={handleOptionKeyDown}
            >
              <span>{company.displayName}</span>
              {isSelected ? <Check size={17} aria-hidden="true" /> : null}
            </Button>
          );
        })}
      </div>
    </dialog>
  );
}

export function CompanySelector(props: CompanySelectorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const focusRestoreTimerRef = useRef<number | null>(null);
  const closeDialog = () => {
    setIsOpen(false);
    if (focusRestoreTimerRef.current !== null) {
      window.clearTimeout(focusRestoreTimerRef.current);
    }
    focusRestoreTimerRef.current = window.setTimeout(() => {
      triggerRef.current?.focus();
      focusRestoreTimerRef.current = null;
    }, 0);
  };

  useEffect(() => () => {
    if (focusRestoreTimerRef.current !== null) {
      window.clearTimeout(focusRestoreTimerRef.current);
    }
  }, []);

  return (
    <div className="bi-company-section">
      <div className="bi-section-heading">
        <Landmark size={17} aria-hidden="true" />
        <h2>기업 선택</h2>
      </div>
      <div className="bi-company-selector">
        <div className="bi-company-selector__current">
          <span>현재 기업</span>
          <strong title={props.selectedName}>{props.selectedName || '준비된 스냅샷 없음'}</strong>
        </div>
        <div className="bi-company-selector__actions">
          <Button
            ref={triggerRef}
            size="sm"
            type="button"
            aria-controls={COMPANY_SELECTOR_DIALOG_ID}
            aria-expanded={isOpen}
            aria-haspopup="dialog"
            disabled={props.companies.length === 0}
            onClick={() => setIsOpen(true)}
          >
            기업 선택
          </Button>
          {props.managementAction}
        </div>
      </div>
      {isOpen ? <CompanySelectorDialog {...props} onClose={closeDialog} /> : null}
    </div>
  );
}
