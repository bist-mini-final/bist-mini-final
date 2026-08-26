import { ResponsiveHeatMap } from '@nivo/heatmap';
import type {
  CellComponentProps,
  HeatMapSerie,
  TooltipProps,
} from '@nivo/heatmap';
import { useState } from 'react';
import { buildFinancialHealthHeatmap } from '../../selectors/financialHealthHeatmap';
import type { FinancialHealthTrend } from '../../selectors/financialHealthHeatmap';
import type { BiDashboardSnapshot, CardSize, PeriodRange } from '../../types';

interface FinancialHealthHeatmapProps {
  readonly dashboard: BiDashboardSnapshot;
  readonly range: PeriodRange;
  readonly size: CardSize;
}

interface NivoHealthDatum {
  readonly x: string;
  readonly y: number | null;
  readonly metricLabel: string;
  readonly directionLabel: string;
  readonly periodLabel: string;
  readonly displayValue: string;
  readonly delta: number | null;
  readonly trend: FinancialHealthTrend;
  readonly trendLabel: string;
}

const CELL_COLORS = {
  baseline: 'var(--bi-health-neutral-bg)',
  'strong-improvement': 'var(--bi-health-strong-positive-bg)',
  improvement: 'var(--bi-health-positive-bg)',
  stable: 'var(--bi-health-neutral-bg)',
  decline: 'var(--bi-health-negative-bg)',
  'strong-decline': 'var(--bi-health-strong-negative-bg)',
  na: 'var(--bi-health-na-bg)',
} as const satisfies Readonly<Record<FinancialHealthTrend, string>>;

const TEXT_COLORS = {
  baseline: 'var(--bi-health-neutral-text)',
  'strong-improvement': 'var(--bi-health-strong-positive-text)',
  improvement: 'var(--bi-health-positive-text)',
  stable: 'var(--bi-health-neutral-text)',
  decline: 'var(--bi-health-negative-text)',
  'strong-decline': 'var(--bi-health-strong-negative-text)',
  na: 'var(--bi-health-na-text)',
} as const satisfies Readonly<Record<FinancialHealthTrend, string>>;

function formatDelta(delta: number | null): string | null {
  if (delta === null) return null;
  const sign = delta > 0 ? '+' : '';
  return `${sign}${delta.toFixed(1)}%p`;
}

function HealthCell(props: CellComponentProps<NivoHealthDatum>) {
  const { cell } = props;
  const width = Math.max(cell.width - 2, 0);
  const height = Math.max(cell.height - 2, 0);
  const delta = formatDelta(cell.data.delta);
  const detail = cell.data.trend === 'na'
    ? null
    : cell.width < 48 || delta === null
      ? cell.data.trendLabel
      : `${cell.data.trendLabel} ${delta}`;
  const valueFontSize = cell.width < 48 ? 7.5 : 10;
  const detailFontSize = cell.width < 48 ? 6 : 7.5;

  return (
    <g
      transform={`translate(${cell.x}, ${cell.y})`}
      data-trend={cell.data.trend}
      onMouseEnter={props.onMouseEnter?.(cell)}
      onMouseMove={props.onMouseMove?.(cell)}
      onMouseLeave={props.onMouseLeave?.(cell)}
      onClick={props.onClick?.(cell)}
    >
      <title>{`${cell.data.periodLabel} ${cell.data.metricLabel} ${cell.data.displayValue}, ${cell.data.trendLabel}${delta ? `, 직전 기간 대비 ${delta}` : ''}`}</title>
      <rect
        x={-width / 2}
        y={-height / 2}
        width={width}
        height={height}
        rx={6}
        fill={cell.color}
        stroke="var(--surface)"
        strokeWidth={1}
      />
      <text
        textAnchor="middle"
        fill={TEXT_COLORS[cell.data.trend]}
        fontWeight={750}
        pointerEvents="none"
      >
        <tspan x={0} y={detail ? -2 : 3} fontSize={valueFontSize}>{cell.data.displayValue}</tspan>
        {detail ? <tspan x={0} y={11} fontSize={detailFontSize}>{detail}</tspan> : null}
      </text>
    </g>
  );
}

function HealthTooltip({ cell }: TooltipProps<NivoHealthDatum>) {
  const delta = formatDelta(cell.data.delta);
  return (
    <div className="bi-chart-tooltip">
      <strong>{cell.data.periodLabel}</strong>
      <ul>
        <li><span>{cell.data.metricLabel}</span><b>{cell.data.displayValue}</b></li>
        <li><span>{cell.data.directionLabel}</span><b>{cell.data.trendLabel}</b></li>
      </ul>
      {delta ? <small>직전 기간 대비 {delta}</small> : null}
    </div>
  );
}

export function FinancialHealthHeatmap(props: FinancialHealthHeatmapProps) {
  const model = buildFinancialHealthHeatmap(props.dashboard, props.range, props.size);
  const [chartWidth, setChartWidth] = useState(600);
  const compact = chartWidth < 480;
  const data: HeatMapSerie<NivoHealthDatum, object>[] = model.rows.map((row) => ({
    id: row.label,
    data: row.cells.map((cell) => ({
      x: cell.periodLabel,
      y: cell.trend === 'na' ? null : cell.delta ?? 0,
      metricLabel: row.label,
      directionLabel: row.direction === 'higher' ? '상승 시 개선' : '하락 시 개선',
      periodLabel: cell.periodLabel,
      displayValue: cell.displayValue,
      delta: cell.delta,
      trend: cell.trend,
      trendLabel: cell.trendLabel,
    })),
  }));

  return (
    <div className="bi-health-heatmap">
      <div className="bi-health-heatmap__legend" aria-label="변화 상태 범례">
        <span data-trend="strong-improvement">큰 개선</span>
        <span data-trend="improvement">개선</span>
        <span data-trend="stable">유지</span>
        <span data-trend="decline">악화</span>
        <span data-trend="strong-decline">큰 악화</span>
        <span data-trend="na">NA</span>
      </div>
      <div
        className="bi-health-heatmap__chart"
        role="img"
        aria-label="기간별 재무 체력 히트맵"
      >
        <ResponsiveHeatMap<NivoHealthDatum, object>
          data={data}
          margin={{ top: compact ? 24 : 28, right: 2, bottom: 2, left: compact ? 68 : 104 }}
          axisTop={{ tickSize: 0, tickPadding: compact ? 5 : 7 }}
          axisRight={null}
          axisBottom={null}
          axisLeft={{ tickSize: 0, tickPadding: compact ? 5 : 8 }}
          colors={(cell) => CELL_COLORS[cell.data.trend]}
          emptyColor={CELL_COLORS.na}
          cellComponent={HealthCell}
          tooltip={HealthTooltip}
          enableLabels={false}
          xInnerPadding={0.02}
          yInnerPadding={0.02}
          activeOpacity={1}
          inactiveOpacity={1}
          hoverTarget="cell"
          animate={false}
          role="presentation"
          defaultWidth={600}
          defaultHeight={300}
          onResize={({ width }) => setChartWidth(width)}
          theme={{
            axis: {
              ticks: {
                text: {
                  fill: 'var(--text-muted)',
                  fontSize: compact ? 7 : 9,
                  fontWeight: 700,
                },
              },
            },
            tooltip: {
              container: {
                padding: 0,
                background: 'transparent',
                boxShadow: 'none',
              },
            },
          }}
        />
      </div>
    </div>
  );
}
