import { useState } from 'react';
import { BiDashboardGrid } from './components/BiDashboardGrid';
import { BiDataState } from './components/BiDataState';
import { BiHeader } from './components/BiHeader';
import { BiPageNotice } from './components/BiPageNotice';
import { BiToolbar } from './components/BiToolbar';
import { CardLibraryDialog } from './components/CardLibraryDialog';
import { CompanySelector } from './components/CompanySelector';
import { EvidenceDialog } from './components/EvidenceDialog';
import { ResetDataDialog } from './components/ResetDataDialog';
import { ResetLayoutDialog } from './components/ResetLayoutDialog';
import { SnapshotManager } from './components/SnapshotManager';
import { getCardDefinition } from './config/cardRegistry';
import { useBiCompanies } from './hooks/useBiCompanies';
import { useBiDashboard } from './hooks/useBiDashboard';
import { useBiLayout } from './hooks/useBiLayout';
import { useSelectedBiCompany } from './hooks/useSelectedBiCompany';
import { buildCardViewModel } from './selectors/cardViewModel';
import type { BiCardId, PeriodRange } from './types';
import 'react-grid-layout/css/styles.css';
import './bi.css';
import './bi-reference.css';

const PERIOD_OPTIONS = ['최근 3개', '최근 5개', '전체'] as const satisfies readonly PeriodRange[];

export function BiPage() {
  const companiesController = useBiCompanies();
  const companiesState = companiesController.state;
  const availableCompanies = companiesState.status === 'ready' ? companiesState.companies : [];
  const companySelection = useSelectedBiCompany(availableCompanies);
  const [selectedPeriod, setSelectedPeriod] = useState<PeriodRange>('최근 5개');
  const [isEditing, setIsEditing] = useState(false);
  const [isLibraryOpen, setIsLibraryOpen] = useState(false);
  const [isResetOpen, setIsResetOpen] = useState(false);
  const [isDataResetOpen, setIsDataResetOpen] = useState(false);
  const [evidenceCardId, setEvidenceCardId] = useState<BiCardId | null>(null);
  const layout = useBiLayout();
  const dashboardController = useBiDashboard(companySelection.selectedCompany);
  const dashboardState = dashboardController.state;

  if (companiesState.status === 'loading') {
    return <BiDataState tone="loading" title="BI 데이터를 불러오는 중입니다" message="등록된 기업 목록을 확인하고 있습니다." />;
  }
  if (companiesState.status === 'error') {
    return <BiDataState tone="error" title="기업 목록을 불러오지 못했습니다" message={companiesState.message} />;
  }
  const companySelector = (
    <CompanySelector
      companies={companiesState.companies}
      selectedId={companySelection.selectedCompanyId}
      selectedName={companySelection.selectedCompany?.displayName ?? ''}
      onRefresh={companiesController.refresh}
      onSelect={companySelection.selectCompany}
      managementAction={(
        <SnapshotManager
          onMaterialized={async (companyId) => {
            companySelection.selectCompany(companyId);
            await companiesController.refresh();
          }}
        />
      )}
    />
  );
  const isDashboardReady = dashboardState.status === 'ready';
  const dashboard = isDashboardReady ? dashboardState.dashboard : null;
  const evidenceCard = dashboard && evidenceCardId ? getCardDefinition(evidenceCardId) : null;
  const evidenceViewModel = evidenceCard && dashboard ? buildCardViewModel({
    definition: evidenceCard,
    dashboard,
    range: selectedPeriod,
    size: 'L',
  }) : null;

  return (
    <section
      className="bi-page"
      aria-labelledby={isDashboardReady ? 'bi-page-title' : undefined}
    >
      {dashboard ? (
        <>
          <BiHeader
            dashboard={dashboard}
            activeAction={dashboardController.activeAction}
            onRefresh={() => void dashboardController.refresh()}
            onReset={() => setIsDataResetOpen(true)}
          />
          <BiPageNotice refresh={dashboard.refresh} />
        </>
      ) : null}

      <div className="bi-page__workspace">
        {companySelector}

        {companiesState.companies.length === 0 ? (
          <BiDataState
            tone="empty"
            title="준비된 기업 스냅샷이 없습니다"
            message="기업 스냅샷 추가에서 인덱싱이 완료된 기업을 선택해 생성할 수 있습니다."
          />
        ) : null}
        {companiesState.companies.length > 0
          && (dashboardState.status === 'idle' || dashboardState.status === 'loading') ? (
          <BiDataState
            tone="loading"
            title="대시보드를 불러오는 중입니다"
            message="게시된 지표 스냅샷을 확인하고 있습니다."
          />
        ) : null}
        {dashboardState.status === 'pending' ? (
          <BiDataState
            tone="loading"
            title="지표 스냅샷을 생성하고 있습니다"
            message={dashboardState.job.message ?? '완료된 스냅샷이 게시되면 대시보드를 볼 수 있습니다.'}
          />
        ) : null}
        {dashboardState.status === 'error' ? (
          <BiDataState
            tone="error"
            title="대시보드를 표시할 수 없습니다"
            message={dashboardState.message}
            actionLabel={companySelection.selectedCompany?.source ? '스냅샷 다시 생성' : undefined}
            onAction={companySelection.selectedCompany?.source
              ? () => { void dashboardController.retryMaterialization(); }
              : undefined}
          />
        ) : null}
        {dashboard ? (
          <>
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
          </>
        ) : null}
      </div>

      {dashboard && isLibraryOpen ? (
        <CardLibraryDialog
          hiddenCardIds={layout.hiddenCardIds}
          onRestore={layout.restoreCard}
          onClose={() => setIsLibraryOpen(false)}
        />
      ) : null}
      {dashboard && evidenceCard && evidenceViewModel ? (
        <EvidenceDialog
          cardTitle={evidenceCard.title}
          evidence={evidenceViewModel.evidence}
          source={dashboard.source}
          snapshotId={dashboard.snapshot.snapshotId}
          onClose={() => setEvidenceCardId(null)}
        />
      ) : null}
      {dashboard && isResetOpen ? (
        <ResetLayoutDialog
          onConfirm={() => { layout.resetLayout(); setIsResetOpen(false); }}
          onClose={() => setIsResetOpen(false)}
        />
      ) : null}
      {dashboard && isDataResetOpen ? (
        <ResetDataDialog
          companyName={dashboard.company.displayName}
          onConfirm={() => {
            setIsDataResetOpen(false);
            void dashboardController.reset();
          }}
          onClose={() => setIsDataResetOpen(false)}
        />
      ) : null}
    </section>
  );
}
