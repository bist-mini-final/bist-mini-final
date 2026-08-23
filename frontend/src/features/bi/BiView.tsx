import { useMemo, useState } from 'react';
import { Landmark } from 'lucide-react';
import { BiDashboardGrid } from './components/BiDashboardGrid';
import { BiHeader } from './components/BiHeader';
import { BiPageNotice } from './components/BiPageNotice';
import { BiToolbar } from './components/BiToolbar';
import { CardLibraryDialog } from './components/CardLibraryDialog';
import { CompanyTabs } from './components/CompanyTabs';
import { EvidenceDialog } from './components/EvidenceDialog';
import { ResetLayoutDialog } from './components/ResetLayoutDialog';
import { getCardDefinition } from './config/cardRegistry';
import { DASHBOARD_FIXTURES } from './fixtures/dashboardFixtures';
import { useBiLayout } from './hooks/useBiLayout';
import { buildCardViewModel } from './selectors/cardViewModel';
import type { BiCardId, PeriodRange } from './types';
import 'react-grid-layout/css/styles.css';
import './bi.css';
import './bi-reference.css';

const PERIOD_OPTIONS = ['최근 3개', '최근 5개', '전체'] as const satisfies readonly PeriodRange[];
const COMPANY_TABS = DASHBOARD_FIXTURES.map((dashboard) => ({
  id: dashboard.company.companyId,
  name: dashboard.company.displayName,
}));

export function BiView() {
  const [selectedCompanyId, setSelectedCompanyId] = useState(COMPANY_TABS[0]?.id ?? '');
  const [selectedPeriod, setSelectedPeriod] = useState<PeriodRange>('최근 5개');
  const [isEditing, setIsEditing] = useState(false);
  const [isLibraryOpen, setIsLibraryOpen] = useState(false);
  const [isResetOpen, setIsResetOpen] = useState(false);
  const [evidenceCardId, setEvidenceCardId] = useState<BiCardId | null>(null);
  const layout = useBiLayout();

  const dashboard = useMemo(
    () => DASHBOARD_FIXTURES.find((item) => item.company.companyId === selectedCompanyId) ?? DASHBOARD_FIXTURES[0],
    [selectedCompanyId],
  );
  const evidenceCard = evidenceCardId ? getCardDefinition(evidenceCardId) : null;
  const evidenceViewModel = evidenceCard ? buildCardViewModel({
    definition: evidenceCard,
    dashboard,
    range: selectedPeriod,
    size: 'L',
  }) : null;

  return (
    <section className="bi-page" aria-labelledby="bi-page-title">
      <BiHeader
        dashboard={dashboard}
        periodLabel={selectedPeriod}
        isRefreshing={false}
        onRefresh={() => {}}
      />
      <BiPageNotice refresh={dashboard.refresh} />

      <div className="bi-page__workspace">
        <div className="bi-company-section">
          <div className="bi-section-heading">
            <Landmark size={17} aria-hidden="true" />
            <h2>기업 선택</h2>
          </div>
          <CompanyTabs
            companies={COMPANY_TABS}
            selectedId={selectedCompanyId}
            onSelect={setSelectedCompanyId}
          />
        </div>

        <BiToolbar
          periodOptions={PERIOD_OPTIONS}
          selectedPeriod={selectedPeriod}
          onPeriodChange={setSelectedPeriod}
          isEditing={isEditing}
          onEditingChange={setIsEditing}
          visibleCardCount={layout.cards.length}
          hiddenCardCount={layout.hiddenCardIds.length}
          onOpenCardLibrary={() => setIsLibraryOpen(true)}
          onResetLayout={() => setIsResetOpen(true)}
        />

        <BiDashboardGrid
          dashboard={dashboard}
          cards={layout.cards}
          periodRange={selectedPeriod}
          isEditing={isEditing}
          canMoveCard={layout.canMoveCard}
          onMoveCard={layout.moveCard}
          onReplaceCards={layout.replaceCards}
          onHideCard={layout.hideCard}
          onShowEvidence={setEvidenceCardId}
        />
      </div>

      {isLibraryOpen ? (
        <CardLibraryDialog
          hiddenCardIds={layout.hiddenCardIds}
          onRestore={layout.restoreCard}
          onClose={() => setIsLibraryOpen(false)}
        />
      ) : null}
      {evidenceCard && evidenceViewModel ? (
        <EvidenceDialog
          cardTitle={evidenceCard.title}
          evidence={evidenceViewModel.evidence}
          source={dashboard.source}
          snapshotId={dashboard.snapshot.snapshotId}
          onClose={() => setEvidenceCardId(null)}
        />
      ) : null}
      {isResetOpen ? (
        <ResetLayoutDialog
          onConfirm={() => { layout.resetLayout(); setIsResetOpen(false); }}
          onClose={() => setIsResetOpen(false)}
        />
      ) : null}
    </section>
  );
}
