import {
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  BenchmarkScatterTooltip,
  renderBenchmarkScatterMarker,
  type BenchmarkScatterPoint,
} from './CompanyComparisonCharts';

interface ComparisonPositionPanelProps {
  readonly companiesCount: number;
  readonly averageCagr: number;
  readonly averageMargin: number;
  readonly comparisonMode: boolean;
  readonly points: readonly BenchmarkScatterPoint[];
  readonly onSelectCompany: (companyId: string) => void;
}

export function ComparisonPositionPanel({
  companiesCount,
  averageCagr,
  averageMargin,
  comparisonMode,
  points,
  onSelectCompany,
}: ComparisonPositionPanelProps) {
  return (
    <section className="interactive-distribution-panel position-analysis-panel" aria-label="기업군 내 성장성과 수익성 위치">
      <div className="distribution-title-row">
        <div>
          <span className="distribution-main-title">성장성 × 수익성 포지션</span>
          <p className="distribution-description">선택 기업이 전체 {companiesCount}개 기업에서 어디에 위치하는지 확인하세요.</p>
        </div>
        <span className="distribution-scope">{companiesCount}개 기업</span>
      </div>
      <div className="distribution-sub-widget benchmark-scatter-widget is-standalone">
        <div className="benchmark-scatter-title-row">
          <span className="dist-widget-heading">평균 기준선: 성장률 {averageCagr.toFixed(1)}% · 이익률 {averageMargin.toFixed(1)}%</span>
          <div className="benchmark-scatter-legend" aria-label="산점도 범례">
            {comparisonMode ? (
              <><span><i className="is-compare-a" />기업 A</span><span><i className="is-compare-b" />기업 B</span></>
            ) : <span><i className="is-selected" />선택 기업</span>}
            <span><i />기타</span>
          </div>
        </div>
        <div
          className="benchmark-scatter-chart"
          role="img"
          aria-label="기업별 매출 성장률과 영업이익률 산점도. 점을 선택하면 표에서 기업이 강조됩니다."
        >
          <span className="quadrant-label is-top-left">안정 수익형</span>
          <span className="quadrant-label is-top-right">고성장·고수익</span>
          <span className="quadrant-label is-bottom-left">관찰 필요</span>
          <span className="quadrant-label is-bottom-right">성장 투자형</span>
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart margin={{ top: 22, right: 16, bottom: 6, left: -4 }}>
              <CartesianGrid stroke="var(--border-subtle)" strokeDasharray="3 3" />
              <XAxis
                type="number"
                dataKey="growth"
                name="매출 성장률"
                unit="%"
                tick={{ fill: 'var(--text-muted)', fontSize: 9 }}
                tickLine={false}
                axisLine={{ stroke: 'var(--border-strong)' }}
                tickCount={5}
                domain={['auto', 'auto']}
              />
              <YAxis
                type="number"
                dataKey="margin"
                name="영업이익률"
                unit="%"
                width={42}
                tick={{ fill: 'var(--text-muted)', fontSize: 9 }}
                tickLine={false}
                axisLine={{ stroke: 'var(--border-strong)' }}
                tickCount={5}
                domain={['auto', 'auto']}
              />
              <ReferenceLine x={averageCagr} stroke="var(--info-600, #2563eb)" strokeDasharray="4 3" />
              <ReferenceLine y={averageMargin} stroke="var(--brand-600)" strokeDasharray="4 3" />
              <Tooltip cursor={{ stroke: 'var(--text-muted)', strokeDasharray: '3 3' }} content={<BenchmarkScatterTooltip />} />
              <Scatter
                data={points}
                shape={renderBenchmarkScatterMarker}
                onClick={(point) => {
                  const companyId = (point as { payload?: BenchmarkScatterPoint }).payload?.companyId;
                  if (companyId) onSelectCompany(companyId);
                }}
              />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
        <div className="benchmark-scatter-axis-labels" aria-hidden="true">
          <span>낮은 성장</span>
          <strong>매출 성장률</strong>
          <span>높은 성장</span>
        </div>
      </div>
    </section>
  );
}
