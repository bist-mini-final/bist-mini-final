import { CartesianGrid, Cell, LabelList, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { buildChartPoints, formatChartAxis, formatChartValue, getChartSeries } from '../../selectors/chartViewModel';
import type { BiDashboardSnapshot, CardSize, PeriodRange } from '../../types';
import { BiChartFrame, BiChartTooltip } from './BiChartFrame';
import { CHART_COLORS, CHART_GEOMETRY } from './chartStyle';

interface FinancialScaleChartProps {
  readonly dashboard: BiDashboardSnapshot;
  readonly range: PeriodRange;
  readonly size: CardSize;
}

const METRICS = ['total_assets', 'total_liabilities', 'total_equity'] as const;

export function FinancialScaleChart({ dashboard, range, size }: FinancialScaleChartProps) {
  const data = buildChartPoints({ dashboard, metricIds: METRICS, range, size });
  const series = getChartSeries(dashboard, METRICS);
  const latest = data[data.length - 1];
  const composition = [
    {
      name: '부채',
      value: Math.max(latest?.values.total_liabilities ?? 0, 0),
      fill: 'url(#bi-scale-liability-gradient)',
    },
    {
      name: '자본',
      value: Math.max(latest?.values.total_equity ?? 0, 0),
      fill: 'url(#bi-scale-equity-gradient)',
    },
  ];
  const compositionTotal = composition.reduce((sum, item) => sum + item.value, 0);
  const chartData = data.map((point) => ({ ...point, totalAssets: point.values.total_assets }));
  return (
    <BiChartFrame title="자산 구성과 규모" description={`최근 ${latest?.periodLabel ?? '기간'} 구성과 총자산 추이입니다.`} data={data} series={series} valueKind="amount">
      <div className="bi-chart-layout bi-financial-scale-chart">
        <div className="bi-financial-scale-chart__composition">
          <strong>자산 구성 ({latest?.periodLabel ?? '최근'})</strong>
          <div className="bi-financial-scale-chart__donut">
            <ResponsiveContainer width="100%" height="100%" minWidth={0}>
              <PieChart accessibilityLayer>
                <defs>
                  <linearGradient id="bi-scale-liability-gradient" x1="0" y1="0" x2="1" y2="1">
                    <stop offset="0%" stopColor={CHART_COLORS.secondary} />
                    <stop offset="100%" stopColor={CHART_COLORS.secondary} stopOpacity={0.66} />
                  </linearGradient>
                  <linearGradient id="bi-scale-equity-gradient" x1="0" y1="0" x2="1" y2="1">
                    <stop offset="0%" stopColor={CHART_COLORS.primary} stopOpacity={0.55} />
                    <stop offset="100%" stopColor={CHART_COLORS.primary} />
                  </linearGradient>
                </defs>
                <Tooltip formatter={(value, name) => [formatChartAxis(Number(value), 'amount'), name]} />
                <Pie data={composition} dataKey="value" nameKey="name" innerRadius="58%" outerRadius="84%" paddingAngle={1} stroke={CHART_COLORS.surface} strokeWidth={2} isAnimationActive={false}>
                  {composition.map((item) => <Cell key={item.name} fill={item.fill} />)}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="bi-financial-scale-chart__legend" aria-label="최근 자산 구성">
            {composition.map((item, index) => (
              <span key={item.name}>
                <i data-tone={index === 0 ? 'liability' : 'equity'} />
                {item.name} {compositionTotal > 0 ? Math.round(item.value / compositionTotal * 100) : 0}% ({formatChartValue(item.value, 'amount')})
              </span>
            ))}
          </div>
        </div>
        <div className="bi-financial-scale-chart__trend">
          <div className="bi-financial-scale-chart__trend-heading">
            <span>총자산 추이</span>
            <strong>{formatChartValue(latest?.values.total_assets ?? 0, 'amount')}</strong>
          </div>
          <div>
            <ResponsiveContainer width="100%" height="100%" minWidth={0}>
              <LineChart data={chartData} margin={{ ...CHART_GEOMETRY.margin, top: 22, right: 12 }} accessibilityLayer>
                <CartesianGrid stroke={CHART_COLORS.grid} strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="periodLabel" tickLine={false} axisLine={false} minTickGap={18} />
                <YAxis tickFormatter={(value: number) => formatChartAxis(value, 'amount')} tickLine={false} axisLine={false} width={42} />
                <Tooltip content={(tooltipProps) => <BiChartTooltip {...tooltipProps} data={data} valueKind="amount" />} />
                <Line
                  type="monotone"
                  dataKey="totalAssets"
                  name="총자산"
                  stroke={CHART_COLORS.primary}
                  strokeWidth={CHART_GEOMETRY.lineWidth}
                  dot={{ r: CHART_GEOMETRY.dotRadius, fill: CHART_COLORS.surface, strokeWidth: 2 }}
                  activeDot={{ r: CHART_GEOMETRY.activeDotRadius }}
                  isAnimationActive={false}
                >
                  <LabelList dataKey="totalAssets" position="top" formatter={(value) => typeof value === 'number' ? formatChartAxis(value, 'amount') : ''} fill={CHART_COLORS.neutral} fontSize={9} />
                </Line>
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </BiChartFrame>
  );
}
