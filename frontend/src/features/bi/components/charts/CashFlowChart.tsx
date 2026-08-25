import { Bar, CartesianGrid, Cell, ComposedChart, LabelList, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { buildChartPoints, formatChartAxis, formatChartValue, getChartSeries } from '../../selectors/chartViewModel';
import type { BiDashboardSnapshot, CardSize, PeriodRange } from '../../types';
import { BiChartFrame, BiChartTooltip } from './BiChartFrame';
import { CHART_COLORS, CHART_GEOMETRY } from './chartStyle';

interface CashFlowChartProps {
  readonly dashboard: BiDashboardSnapshot;
  readonly range: PeriodRange;
  readonly size: CardSize;
}

const METRICS = ['operating_cash_flow', 'capital_expenditure', 'free_cash_flow'] as const;

export function CashFlowChart({ dashboard, range, size }: CashFlowChartProps) {
  const data = buildChartPoints({ dashboard, metricIds: METRICS, range, size });
  const series = getChartSeries(dashboard, METRICS);
  const unit = dashboard.metrics.operating_cash_flow ?? dashboard.metrics.free_cash_flow ?? null;
  const latest = [...data].reverse().find(
    (pt) => pt.values.operating_cash_flow !== null && pt.values.operating_cash_flow !== undefined
  ) ?? data[data.length - 1];
  const operatingCashFlow = latest?.values.operating_cash_flow ?? 0;
  const capitalExpenditure = latest?.values.capital_expenditure ?? 0;
  const freeCashFlow = latest?.values.free_cash_flow ?? 0;
  const waterfallData = [
    { label: '영업현금흐름', range: [0, operatingCashFlow], end: operatingCashFlow, rawValue: operatingCashFlow, color: CHART_COLORS.primary },
    {
      label: 'CapEx',
      range: [Math.min(freeCashFlow, operatingCashFlow), Math.max(freeCashFlow, operatingCashFlow)],
      end: freeCashFlow,
      rawValue: capitalExpenditure,
      color: CHART_COLORS.secondary,
    },
    { label: 'FCF', range: [0, freeCashFlow], end: freeCashFlow, rawValue: freeCashFlow, color: CHART_COLORS.primary },
  ];
  return (
    <BiChartFrame title="현금흐름 브리지" description={`최근 ${latest?.periodLabel ?? '기간'}의 FCF 형성과 추이를 봅니다.`} data={data} series={series} valueKind="amount" unit={unit}>
      <div className="bi-chart-layout bi-cash-flow-chart">
        <div className="bi-cash-flow-chart__summary">
          <span>잉여현금흐름</span>
          <strong>{formatChartValue(freeCashFlow, 'amount', unit)}</strong>
          <small>영업현금흐름 {formatChartValue(operatingCashFlow, 'amount', unit)}</small>
        </div>
        <div className="bi-cash-flow-chart__trend" aria-label="FCF 기간 추이">
          <strong>FCF (최근 {data.length}개)</strong>
          <div>
            <ResponsiveContainer width="100%" height="100%" minWidth={0}>
              <LineChart data={data} margin={{ top: 8, right: 7, bottom: 0, left: 7 }} accessibilityLayer>
                <XAxis dataKey="periodLabel" tickLine={false} axisLine={false} interval="preserveStartEnd" />
                <YAxis hide domain={['dataMin', 'dataMax']} />
                <Tooltip content={(tooltipProps) => <BiChartTooltip {...tooltipProps} data={data} valueKind="amount" unit={unit} />} />
                <Line
                  type="monotone"
                  dataKey={(point) => point.values.free_cash_flow ?? null}
                  name="잉여현금흐름"
                  stroke={CHART_COLORS.primary}
                  strokeWidth={CHART_GEOMETRY.lineWidth}
                  dot={{ r: CHART_GEOMETRY.dotRadius, fill: CHART_COLORS.surface, strokeWidth: 2 }}
                  activeDot={{ r: CHART_GEOMETRY.activeDotRadius }}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="bi-cash-flow-chart__waterfall">
          <strong>현금흐름 구성 ({latest?.periodLabel ?? '최근'})</strong>
          <ResponsiveContainer width="100%" height="100%" minWidth={0}>
            <ComposedChart data={waterfallData} margin={{ top: 18, right: 8, bottom: 0, left: 0 }} accessibilityLayer>
              <CartesianGrid stroke={CHART_COLORS.grid} strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="label" tickLine={false} axisLine={false} />
              <YAxis tickFormatter={(value: number) => formatChartAxis(value, 'amount', unit)} tickLine={false} axisLine={false} width={48} />
              <ReferenceLine y={0} stroke={CHART_COLORS.neutral} />
              <Tooltip
                cursor={{ fill: 'transparent' }}
                formatter={(_value, _name, item) => [formatChartValue(item.payload.rawValue, 'amount', unit), item.payload.label]}
              />
              <Line type="stepAfter" dataKey="end" stroke={CHART_COLORS.neutral} strokeDasharray="3 3" strokeWidth={1} dot={false} activeDot={false} isAnimationActive={false} />
              <Bar dataKey="range" barSize={36} radius={[3, 3, 0, 0]} isAnimationActive={false}>
                {waterfallData.map((item) => <Cell key={item.label} fill={item.color} />)}
                <LabelList dataKey="rawValue" position="top" formatter={(value) => typeof value === 'number' ? formatChartAxis(value, 'amount', unit) : ''} fill={CHART_COLORS.neutral} fontSize={9} />
              </Bar>
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>
    </BiChartFrame>
  );
}
