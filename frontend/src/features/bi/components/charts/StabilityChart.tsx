import { ArrowLeft, ArrowRight } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { buildChartPoints, formatChartAxis, formatChartValue, getChartSeries } from '../../selectors/chartViewModel';
import type { BiDashboardSnapshot, CardSize, PeriodRange } from '../../types';
import { BiChartFrame } from './BiChartFrame';
import { CHART_COLORS } from './chartStyle';

interface StabilityChartProps {
  readonly dashboard: BiDashboardSnapshot;
  readonly range: PeriodRange;
  readonly size: CardSize;
}

const METRICS = ['cash_and_short_term_investments', 'total_debt', 'net_debt'] as const;

export function StabilityChart({ dashboard, range, size }: StabilityChartProps) {
  const data = buildChartPoints({ dashboard, metricIds: METRICS, range, size });
  const series = getChartSeries(dashboard, METRICS);
  const latest = data[data.length - 1];
  const cashValue = latest?.values.cash_and_short_term_investments ?? null;
  const debtValue = latest?.values.total_debt ?? null;
  const netDebt = latest?.values.net_debt ?? null;
  const cash = Math.abs(cashValue ?? 0);
  const debt = Math.abs(debtValue ?? 0);
  const comparison = [
    {
      label: latest?.periodLabel ?? '최근',
      cash: cashValue === null ? null : -cash,
      debt: debtValue === null ? null : debt,
    },
  ];
  const plotPadding = Math.max(cash + debt, 1) * 0.05;
  const zeroPosition = ((cash + plotPadding) / (cash + debt + plotPadding * 2)) * 100;
  return (
    <BiChartFrame title="현금·차입금 균형" description="현금은 왼쪽, 차입금은 오른쪽으로 비교합니다." data={data} series={series} valueKind="amount">
      <div className="bi-chart-layout bi-stability-chart">
        <div className="bi-stability-chart__labels" aria-hidden="true">
          <span><b>현금</b><strong>{formatChartValue(cashValue === null ? null : cash, 'amount')}</strong><ArrowLeft size={15} /></span>
          <span><b>총차입금</b><strong>{formatChartValue(debtValue === null ? null : debt, 'amount')}</strong><ArrowRight size={15} /></span>
        </div>
        <div className="bi-stability-chart__plot">
          <ResponsiveContainer width="100%" height="100%" minWidth={0}>
            <BarChart data={comparison} layout="vertical" margin={{ top: 10, right: 0, bottom: 4, left: 0 }} stackOffset="sign" accessibilityLayer>
              <defs>
                <pattern id="bi-stability-cash-pattern" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(36)">
                  <rect width="6" height="6" fill={CHART_COLORS.primary} />
                  <line x1="0" y1="0" x2="0" y2="6" stroke={CHART_COLORS.surface} strokeOpacity={0.55} strokeWidth="2" />
                </pattern>
                <pattern id="bi-stability-debt-pattern" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(36)">
                  <rect width="6" height="6" fill={CHART_COLORS.secondary} />
                  <line x1="0" y1="0" x2="0" y2="6" stroke={CHART_COLORS.surface} strokeOpacity={0.7} strokeWidth="2" />
                </pattern>
              </defs>
              <CartesianGrid stroke={CHART_COLORS.grid} strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" domain={[-cash - plotPadding, debt + plotPadding]} ticks={[-cash, 0, debt]} interval={0} tickFormatter={(value: number) => formatChartAxis(Math.abs(value), 'amount')} tickLine={false} axisLine={false} />
              <YAxis type="category" dataKey="label" hide />
              <ReferenceLine x={0} stroke={CHART_COLORS.neutral} />
              <Tooltip formatter={(value, name) => [formatChartValue(Math.abs(Number(value)), 'amount'), name === 'cash' ? '현금' : '차입금']} />
              <Bar dataKey="cash" name="현금" stackId="balance" fill="url(#bi-stability-cash-pattern)" barSize={34} radius={[4, 0, 0, 4]} isAnimationActive={false} />
              <Bar dataKey="debt" name="차입금" stackId="balance" fill="url(#bi-stability-debt-pattern)" barSize={34} radius={[0, 4, 4, 0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
          <div className="bi-stability-chart__net-debt" style={{ left: `${zeroPosition}%` }}>
            <span>순차입금</span><strong>{formatChartValue(netDebt, 'amount')}</strong>
          </div>
        </div>
      </div>
    </BiChartFrame>
  );
}
