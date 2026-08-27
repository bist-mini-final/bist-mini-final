import { useState } from 'react';
import { Landmark } from 'lucide-react';
import { BiDashboardGrid } from './components/BiDashboardGrid';
import { BiDataState } from './components/BiDataState';
import { BiHeader } from './components/BiHeader';
import { BiPageNotice } from './components/BiPageNotice';
import { BiToolbar } from './components/BiToolbar';
import { CardLibraryDialog } from './components/CardLibraryDialog';
import { CompanyTabs } from './components/CompanyTabs';
import { EvidenceDialog } from './components/EvidenceDialog';
import { ResetDataDialog } from './components/ResetDataDialog';
import { ResetLayoutDialog } from './components/ResetLayoutDialog';
import { getCardDefinition } from './config/cardRegistry';
import { useBiCompanies } from './hooks/useBiCompanies';
import { useBiDashboard } from './hooks/useBiDashboard';
import { useBiLayout } from './hooks/useBiLayout';
import { buildCardViewModel } from './selectors/cardViewModel';
import type { BiCardId, PeriodRange } from './types';
import 'react-grid-layout/css/styles.css';
import './bi.css';
import './bi-reference.css';

const PERIOD_OPTIONS = ['최근 3개', '최근 5개', '전체'] as const satisfies readonly PeriodRange[];
const SELECTED_COMPANY_KEY = 'rag-flow:bi-selected-company:v1';

function readSelectedCompanyId(): string {
  try {
    return window.localStorage.getItem(SELECTED_COMPANY_KEY) ?? '';
  } catch (error) {
    if (error instanceof DOMException) return '';
    throw error;
  }
}

function storeSelectedCompanyId(companyId: string): void {
  try {
    window.localStorage.setItem(SELECTED_COMPANY_KEY, companyId);
  } catch (error) {
    if (!(error instanceof DOMException)) throw error;
  }
}

export function BiPage() {
  const companiesState = useBiCompanies();
  const [selectedCompanyId, setSelectedCompanyId] = useState(readSelectedCompanyId);
  const [selectedPeriod, setSelectedPeriod] = useState<PeriodRange>('최근 5개');
  const [isEditing, setIsEditing] = useState(false);
  const [isLibraryOpen, setIsLibraryOpen] = useState(false);
  const [isResetOpen, setIsResetOpen] = useState(false);
  const [isDataResetOpen, setIsDataResetOpen] = useState(false);
  const [evidenceCardId, setEvidenceCardId] = useState<BiCardId | null>(null);
  const layout = useBiLayout();
  const resolvedCompanyId = companiesState.status === 'ready'
    ? companiesState.companies.some((company) => company.companyId === selectedCompanyId)
      ? selectedCompanyId
      : companiesState.companies[0]?.companyId ?? ''
    : selectedCompanyId;
  const selectedCompany = companiesState.status === 'ready'
    ? companiesState.companies.find((candidate) => candidate.companyId === resolvedCompanyId) ?? null
    : null;
  const dashboardController = useBiDashboard(selectedCompany);
  const dashboardState = dashboardController.state;

  if (companiesState.status === 'loading') {
    return <BiDataState tone="loading" title="BI 데이터를 불러오는 중입니다" message="등록된 기업 목록을 확인하고 있습니다." />;
  }
  if (companiesState.status === 'error') {
    return <BiDataState tone="error" title="기업 목록을 불러오지 못했습니다" message={companiesState.message} />;
  }
  if (companiesState.companies.length === 0) {
    return <BiDataState tone="empty" title="등록된 기업이 없습니다" message="인덱싱 완료 후 BI materialization을 시작하면 대시보드가 표시됩니다." />;
  }
  const companyTabs = companiesState.companies.map((company) => ({
    id: company.companyId,
    name: company.displayName,
  }));
  const companySelector = (
    <div className="bi-company-section">
      <div className="bi-section-heading">
        <Landmark size={17} aria-hidden="true" />
        <h2>기업 선택</h2>
      </div>
      <CompanyTabs
        companies={companyTabs}
        selectedId={resolvedCompanyId}
        onSelect={(companyId) => {
          setSelectedCompanyId(companyId);
          storeSelectedCompanyId(companyId);
        }}
      />
    </div>
  );
  if (dashboardState.status === 'idle' || dashboardState.status === 'loading') {
    return <BiDataState tone="loading" title="대시보드를 불러오는 중입니다" message="게시된 지표 스냅샷을 확인하고 있습니다.">{companySelector}</BiDataState>;
  }
  if (dashboardState.status === 'pending') {
    return <BiDataState tone="loading" title="지표 스냅샷을 생성하고 있습니다" message={dashboardState.job.message ?? '완료된 스냅샷이 게시되면 대시보드를 볼 수 있습니다.'}>{companySelector}</BiDataState>;
  }
  if (dashboardState.status === 'error') {
    return (
      <BiDataState
        tone="error"
        title="대시보드를 표시할 수 없습니다"
        message={dashboardState.message}
        actionLabel={selectedCompany?.source ? '스냅샷 다시 생성' : undefined}
        onAction={selectedCompany?.source
          ? () => { void dashboardController.retryMaterialization(); }
          : undefined}
      >
        {companySelector}
      </BiDataState>
    );
  }

  const dashboard = dashboardState.dashboard;
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
        activeAction={dashboardController.activeAction}
        onRefresh={() => void dashboardController.refresh()}
        onReset={() => setIsDataResetOpen(true)}
      />
      <BiPageNotice refresh={dashboard.refresh} />

      <div className="bi-page__workspace">
        {companySelector}

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
      {isDataResetOpen ? (
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
