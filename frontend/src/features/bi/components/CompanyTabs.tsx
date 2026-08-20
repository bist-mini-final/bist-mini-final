import type { KeyboardEvent } from 'react';

interface BiCompanyTab {
  readonly id: string;
  readonly name: string;
}

interface CompanyTabsProps {
  readonly companies: readonly BiCompanyTab[];
  readonly selectedId: string;
  readonly onSelect: (companyId: string) => void;
}

export function CompanyTabs({ companies, selectedId, onSelect }: CompanyTabsProps) {
  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>, companyId: string) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onSelect(companyId);
      return;
    }
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;

    const tabs = Array.from(
      event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]') ?? [],
    );
    const currentIndex = tabs.indexOf(event.currentTarget);
    if (currentIndex < 0 || tabs.length === 0) return;

    event.preventDefault();
    const direction = event.key === 'ArrowRight' ? 1 : -1;
    const nextIndex = (currentIndex + direction + tabs.length) % tabs.length;
    const nextTab = tabs[nextIndex];
    if (!nextTab) return;

    nextTab.focus();
  };

  return (
    <div className="bi-company-tabs__scroller">
      <div className="bi-company-tabs" role="tablist" aria-label="기업 선택">
        {companies.map((company) => {
          const isSelected = company.id === selectedId;
          return (
            <button
              key={company.id}
              className="bi-company-tab"
              type="button"
              role="tab"
              aria-selected={isSelected}
              aria-controls="bi-dashboard"
              tabIndex={isSelected ? 0 : -1}
              onClick={() => onSelect(company.id)}
              onKeyDown={(event) => handleKeyDown(event, company.id)}
              title={company.name}
            >
              {company.name}
            </button>
          );
        })}
      </div>
    </div>
  );
}
