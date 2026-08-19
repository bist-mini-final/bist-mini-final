import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { buildChartPoints, formatChartValue, getChartSeries } from '../../selectors/chartViewModel';
import type { BiDashboardSnapshot, CardSize, PeriodRange } from '../../types';
import { BiChartFrame, BiChartTooltip } from './BiChartFrame';
import { CHART_COLORS, CHART_GEOMETRY } from './chartStyle';

interface RevenueChartProps {
  readonly dashboard: BiDashboardSnapshot;
  readonly range: PeriodRange;
  readonly size: CardSize;
}

const METRICS = ['revenue'] as const;

export function RevenueChart({ dashboard, range, size }: RevenueChartProps) {
  const data = buildChartPoints({ dashboard, metricIds: METRICS, range, size });
  const series = getChartSeries(dashboard, METRICS);
  return (
    <BiChartFrame title="매출 추이" description="기간별 값과 변화 방향을 함께 표시합니다." data={data} series={series} valueKind="amount">
      <div className="bi-chart-layout bi-revenue-chart">
        <div className="bi-chart-plot">
          <ResponsiveContainer width="100%" height="100%" minWidth={0}>
            <AreaChart data={data} margin={{ ...CHART_GEOMETRY.margin, left: 8 }} accessibilityLayer>
              <defs>
                <linearGradient id="bi-revenue-area-gradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={CHART_COLORS.secondary} stopOpacity={0.72} />
                  <stop offset="100%" stopColor={CHART_COLORS.secondary} stopOpacity={0.08} />
                </linearGradient>
              </defs>
              <XAxis dataKey="periodLabel" tickLine={false} axisLine={false} minTickGap={18} />
              <YAxis hide domain={['dataMin', 'dataMax']} />
              <Tooltip content={(tooltipProps) => <BiChartTooltip {...tooltipProps} data={data} valueKind="amount" />} />
              <Area
                type="monotone"
                dataKey={(point) => point.values.revenue ?? null}
                name="매출"
                stroke={CHART_COLORS.primary}
                strokeWidth={CHART_GEOMETRY.lineWidth}
                fill="url(#bi-revenue-area-gradient)"
                fillOpacity={1}
                dot={{ r: CHART_GEOMETRY.dotRadius, fill: CHART_COLORS.surface, stroke: CHART_COLORS.primary, strokeWidth: 2 }}
                activeDot={{ r: CHART_GEOMETRY.activeDotRadius }}
                connectNulls={false}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <div className="bi-revenue-values" aria-label="기간별 매출 값">
          {data.map((point) => (
            <div key={point.periodId}>
              <span>{point.periodLabel}</span>
              <strong>{formatChartValue(point.values.revenue ?? null, 'amount')}</strong>
            </div>
          ))}
        </div>
      </div>
    </BiChartFrame>
  );
}
