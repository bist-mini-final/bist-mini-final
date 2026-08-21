import type { BiCardId, BiDashboardSnapshot, CardSize, PeriodRange } from '../../types';
import { CashFlowChart } from './CashFlowChart';
import { FinancialScaleChart } from './FinancialScaleChart';
import { ProfitabilityChart } from './ProfitabilityChart';
import { RevenueChart } from './RevenueChart';
import { StabilityChart } from './StabilityChart';

interface BiCardChartProps {
  readonly cardId: BiCardId;
  readonly dashboard: BiDashboardSnapshot;
  readonly range: PeriodRange;
  readonly size: CardSize;
}

function assertNever(value: never): never {
  throw new TypeError(`처리하지 않은 BI 카드입니다: ${String(value)}`);
}

export function BiCardChart(props: BiCardChartProps) {
  switch (props.cardId) {
    case 'revenue_growth':
      return <RevenueChart dashboard={props.dashboard} range={props.range} size={props.size} />;
    case 'profitability':
      return <ProfitabilityChart dashboard={props.dashboard} range={props.range} size={props.size} />;
    case 'cash_flow':
      return <CashFlowChart dashboard={props.dashboard} range={props.range} size={props.size} />;
    case 'stability':
      return <StabilityChart dashboard={props.dashboard} range={props.range} size={props.size} />;
    case 'financial_scale':
      return <FinancialScaleChart dashboard={props.dashboard} range={props.range} size={props.size} />;
    default:
      return assertNever(props.cardId);
  }
}
