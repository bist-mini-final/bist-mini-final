import { CartesianGrid, LabelList, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { buildChartPoints, formatChartAxis, getChartSeries } from '../../selectors/chartViewModel';
import type { BiDashboardSnapshot, CardSize, PeriodRange } from '../../types';
import { BiChartFrame, BiChartTooltip } from './BiChartFrame';
import { CHART_COLORS, CHART_GEOMETRY } from './chartStyle';

interface ProfitabilityChartProps {
  readonly dashboard: BiDashboardSnapshot;
  readonly range: PeriodRange;
  readonly size: CardSize;
}

const METRICS = ['operating_margin', 'net_margin'] as const;

export function ProfitabilityChart({ dashboard, range, size }: ProfitabilityChartProps) {
  const data = buildChartPoints({ dashboard, metricIds: METRICS, range, size });
  const series = getChartSeries(dashboard, METRICS);
  const chartData = data.map((point) => ({
    ...point,
    operatingMargin: point.values.operating_margin,
    netMargin: point.values.net_margin,
  }));

  return (
    <BiChartFrame title="수익성 흐름" description="영업이익률과 순이익률을 같은 축에서 비교합니다." data={data} series={series} valueKind="percent">
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <LineChart data={chartData} margin={{ ...CHART_GEOMETRY.margin, top: 12, right: 10, bottom: 0 }} accessibilityLayer>
          <CartesianGrid stroke={CHART_COLORS.grid} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="periodLabel" tickLine={false} axisLine={false} minTickGap={20} />
          <YAxis domain={[0, 20]} ticks={[0, 5, 10, 15, 20]} tickFormatter={(value: number) => formatChartAxis(value, 'percent')} tickLine={false} axisLine={false} width={34} />
          <Tooltip content={(tooltipProps) => <BiChartTooltip {...tooltipProps} data={data} valueKind="percent" />} />
          <Legend verticalAlign="top" align="right" iconType="plainline" wrapperStyle={{ top: 0, fontSize: 10 }} />
          <Line
            type="monotone"
            dataKey="operatingMargin"
            name={series[0]?.label ?? ''}
            stroke={CHART_COLORS.primary}
            strokeWidth={CHART_GEOMETRY.lineWidth}
            dot={{ r: CHART_GEOMETRY.dotRadius, fill: CHART_COLORS.surface, strokeWidth: 2 }}
            activeDot={{ r: CHART_GEOMETRY.activeDotRadius }}
            connectNulls={false}
            isAnimationActive={false}
          >
            <LabelList dataKey="operatingMargin" position="top" formatter={(value) => typeof value === 'number' ? `${value.toFixed(1)}%` : ''} fill={CHART_COLORS.neutral} fontSize={9} />
          </Line>
          <Line
            type="monotone"
            dataKey="netMargin"
            name={series[1]?.label ?? ''}
            stroke={CHART_COLORS.secondary}
            strokeWidth={CHART_GEOMETRY.lineWidth}
            strokeDasharray="5 4"
            dot={{ r: CHART_GEOMETRY.dotRadius, fill: CHART_COLORS.surface, strokeWidth: 2 }}
            activeDot={{ r: CHART_GEOMETRY.activeDotRadius }}
            connectNulls={false}
            isAnimationActive={false}
          >
            <LabelList dataKey="netMargin" position="bottom" formatter={(value) => typeof value === 'number' ? `${value.toFixed(1)}%` : ''} fill={CHART_COLORS.neutral} fontSize={9} />
          </Line>
        </LineChart>
      </ResponsiveContainer>
    </BiChartFrame>
  );
}
