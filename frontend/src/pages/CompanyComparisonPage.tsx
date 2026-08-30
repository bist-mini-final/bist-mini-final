import {
  AlertCircle,
  Clock,
  Database,
  RefreshCw,
} from 'lucide-react';
import { Button } from '../shared/ui';
import { CompanyAnalysisPanel } from '../features/company-comparison/CompanyAnalysisPanel';
import {
  CompanyRankingTable,
  ComparisonRankingToolbar,
} from '../features/company-comparison/ComparisonRanking';
import { ComparisonPositionPanel } from '../features/company-comparison/ComparisonPositionPanel';
import { RANKING_METRICS } from '../features/company-comparison/metricRanking';
import { useCompanyComparisonController } from '../features/company-comparison/useCompanyComparisonController';
import '../features/company-comparison/company-comparison.css';
import '../features/company-comparison/comparison-position.css';

export function CompanyComparisonPage() {
  const comparison = useCompanyComparisonController();
  const {
    state,
    companies: filteredCompanies,
    rankingMetric,
    displayDirection,
    selectedCompanyIds,
    focusedCompanyId,
    displayedCompanies,
    comparisonCompanies,
    averageCagr,
    averageMargin,
    benchmarkScatterData,
    activeRankingLabel,
    metricDirectionLabel,
  } = comparison;

  if (state.status === 'loading') {
    return (
      <section className="financial-league-page league-loading" aria-live="polite">
        <RefreshCw size={24} className="spin" />
        <strong>기업 비교 스냅샷을 불러오고 있습니다...</strong>
      </section>
    );
  }

  if (state.status === 'error') {
    return (
      <section className="financial-league-page league-loading" role="alert">
        <AlertCircle size={28} color="#dc2626" />
        <strong>데이터 로드 실패</strong>
        <p>{state.message}</p>
        <Button variant="primary" type="button" onClick={comparison.refresh}>
          스냅샷 생성
        </Button>
      </section>
    );
  }

  return (
    <section className="financial-league-page" aria-label="기업 랭킹 리그 화면">
      <h1 className="page-visually-hidden">기업 비교</h1>

      {state.data.snapshot.status === 'partial' && (
        <section className="comparison-state-card comparison-state-card--error" role="status">
          <AlertCircle size={20} />
          <div><strong>일부 기업이 비교에서 제외되었습니다.</strong><p>{state.data.exclusions.map((item) => item.displayName).join(', ')}</p></div>
        </section>
      )}

      <ComparisonRankingToolbar
        rankingMetric={rankingMetric}
        activeRankingLabel={activeRankingLabel}
        metricDirectionLabel={metricDirectionLabel}
        onMetricChange={comparison.selectRankingMetric}
        onReset={comparison.resetRanking}
        onRefresh={comparison.refresh}
      />

      {/* =========================================================================
          2. Main Layout: Left Table (70%) vs Right Spotlight Cards & Metrics (30%)
         ========================================================================= */}
      <div className="league-main-grid">
        <CompanyRankingTable
          companies={displayedCompanies}
          rankingMetric={rankingMetric}
          displayDirection={displayDirection}
          activeRankingLabel={activeRankingLabel}
          focusedCompanyId={focusedCompanyId}
          selectedCompanyIds={selectedCompanyIds}
          onMetricChange={comparison.selectRankingMetric}
          onFocusCompany={comparison.focusCompany}
          onToggleCompany={comparison.toggleCompany}
        />

        {/* Right Column: selection-driven company analysis */}
        <div className="league-side-column">
          <CompanyAnalysisPanel
            comparison={comparison}
            assumptions={state.data.assumptions}
          />
          <ComparisonPositionPanel
            companiesCount={filteredCompanies.length}
            averageCagr={averageCagr}
            averageMargin={averageMargin}
            comparisonMode={comparisonCompanies.length === 2}
            points={benchmarkScatterData}
            onSelectCompany={comparison.focusCompany}
          />
        </div>
      </div>

      {/* =========================================================================
          3. Bottom Status Footer Bar
         ========================================================================= */}
      <footer className="league-bottom-status-bar" aria-label="데이터 상태">
        <div className="footer-left-links">
          <span className="footer-link-item">
            <Database size={11} /> 데이터 출처: 검증된 BI 스냅샷 {state.data.snapshot.sourceSnapshotIds.length}개 · 원본 셀 근거 {state.data.evidence.length}건
          </span>
          <span className="footer-link-item">
            <RefreshCw size={11} /> 현재 순위: {RANKING_METRICS[rankingMetric].label} 기준 · {metricDirectionLabel}
          </span>
        </div>
        <div className="footer-right-time">
          <span className="footer-link-item">
            <Clock size={11} /> 최종 업데이트: {new Date(state.data.snapshot.generatedAt).toLocaleString('ko-KR')}
          </span>
        </div>
      </footer>
    </section>
  );
}
