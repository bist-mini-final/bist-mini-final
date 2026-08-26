import {
  Activity,
  BadgeDollarSign,
  ChartNoAxesCombined,
  Scale,
  ShieldCheck,
  WalletCards,
  type LucideIcon,
} from 'lucide-react';
import type { BiCardId, BiCardLayoutItem, CardSize, MetricId } from '../types';

export interface BiCardDefinition {
  readonly id: BiCardId;
  readonly title: string;
  readonly description: string;
  readonly icon: LucideIcon;
  readonly primaryMetric: MetricId;
  readonly secondaryMetric: MetricId | null;
  readonly detailMetrics: readonly MetricId[];
  readonly requiredMetrics: readonly MetricId[];
  readonly defaultSize: CardSize;
  readonly allowedSizes: readonly CardSize[];
  readonly defaultWideSpan: number;
  readonly defaultWideHeight: number;
}

export const CARD_REGISTRY = [
  {
    id: 'revenue_growth',
    title: '매출 및 성장',
    description: '매출 흐름과 전년 대비 변화를 확인합니다.',
    icon: ChartNoAxesCombined,
    primaryMetric: 'revenue',
    secondaryMetric: 'revenue_yoy_growth',
    detailMetrics: ['revenue_yoy_growth'],
    requiredMetrics: ['revenue', 'revenue_yoy_growth'],
    defaultSize: 'M',
    allowedSizes: ['S', 'M', 'L'],
    defaultWideSpan: 5.8,
    defaultWideHeight: 12,
  },
  {
    id: 'profitability',
    title: '수익성',
    description: '영업이익과 순이익의 흐름을 살펴봅니다.',
    icon: BadgeDollarSign,
    primaryMetric: 'operating_income',
    secondaryMetric: 'operating_margin',
    detailMetrics: ['operating_margin', 'net_income', 'net_margin'],
    requiredMetrics: ['operating_income', 'operating_margin', 'net_income', 'net_margin'],
    defaultSize: 'M',
    allowedSizes: ['S', 'M', 'L'],
    defaultWideSpan: 5,
    defaultWideHeight: 12,
  },
  {
    id: 'cash_flow',
    title: '현금흐름',
    description: '영업현금흐름과 CapEx, FCF 구성을 확인합니다.',
    icon: WalletCards,
    primaryMetric: 'free_cash_flow',
    secondaryMetric: 'operating_cash_flow',
    detailMetrics: ['operating_cash_flow', 'capital_expenditure'],
    requiredMetrics: ['operating_cash_flow', 'capital_expenditure', 'free_cash_flow'],
    defaultSize: 'M',
    allowedSizes: ['S', 'M', 'L'],
    defaultWideSpan: 6.2,
    defaultWideHeight: 12,
  },
  {
    id: 'stability',
    title: '재무 안정성',
    description: '현금과 총차입금, 순차입금의 균형을 보여줍니다.',
    icon: ShieldCheck,
    primaryMetric: 'net_debt',
    secondaryMetric: 'total_debt',
    detailMetrics: ['cash_and_short_term_investments', 'total_debt'],
    requiredMetrics: ['cash_and_short_term_investments', 'total_debt', 'net_debt'],
    defaultSize: 'M',
    allowedSizes: ['S', 'M', 'L'],
    defaultWideSpan: 8.2,
    defaultWideHeight: 10.7,
  },
  {
    id: 'financial_scale',
    title: '재무 규모',
    description: '자산, 부채, 자본의 전체 규모를 한눈에 봅니다.',
    icon: Scale,
    primaryMetric: 'total_assets',
    secondaryMetric: 'total_equity',
    detailMetrics: ['total_liabilities', 'total_equity'],
    requiredMetrics: ['total_assets', 'total_liabilities', 'total_equity'],
    defaultSize: 'L',
    allowedSizes: ['M', 'L'],
    defaultWideSpan: 8.8,
    defaultWideHeight: 10.7,
  },
  {
    id: 'financial_health_heatmap',
    title: '재무 체력 히트맵',
    description: '핵심 비율의 기간별 개선과 악화를 한눈에 비교합니다.',
    icon: Activity,
    primaryMetric: 'operating_margin',
    secondaryMetric: 'debt_ratio',
    detailMetrics: [
      'revenue_yoy_growth',
      'net_margin',
      'free_cash_flow_margin',
      'net_debt_ratio',
    ],
    requiredMetrics: [
      'revenue_yoy_growth',
      'operating_margin',
      'net_margin',
      'free_cash_flow_margin',
      'debt_ratio',
      'net_debt_ratio',
    ],
    defaultSize: 'L',
    allowedSizes: ['M', 'L'],
    defaultWideSpan: 17,
    defaultWideHeight: 14,
  },
] as const satisfies readonly BiCardDefinition[];

const CARD_IDS = CARD_REGISTRY.map((card) => card.id);

export const DEFAULT_CARD_LAYOUT = [
  {
    cardId: 'revenue_growth', rowId: 'row-primary', size: 'M', x: 0, y: 0,
    gridSizes: { wide: { w: 5.8, h: 12 }, medium: { w: 4, h: 12 } },
  },
  {
    cardId: 'profitability', rowId: 'row-primary', size: 'M', x: 5.8, y: 0,
    gridSizes: { wide: { w: 5, h: 12 }, medium: { w: 4, h: 12 } },
  },
  {
    cardId: 'cash_flow', rowId: 'row-primary', size: 'M', x: 10.8, y: 0,
    gridSizes: { wide: { w: 6.2, h: 12 }, medium: { w: 4, h: 12 } },
  },
  {
    cardId: 'stability', rowId: 'row-secondary', size: 'M', x: 0, y: 12,
    gridSizes: { wide: { w: 8.2, h: 10.7 }, medium: { w: 4, h: 12 } },
  },
  {
    cardId: 'financial_scale', rowId: 'row-secondary', size: 'L', x: 8.2, y: 12,
    gridSizes: { wide: { w: 8.8, h: 10.7 }, medium: { w: 8, h: 14 } },
  },
] as const satisfies readonly BiCardLayoutItem[];

export const DEFAULT_HIDDEN_CARD_IDS = ['financial_health_heatmap'] as const satisfies readonly BiCardId[];

export function getCardDefinition(cardId: BiCardId): BiCardDefinition {
  const card = CARD_REGISTRY.find((candidate) => candidate.id === cardId);
  if (card) return card;
  throw new RangeError(`Unknown BI card: ${cardId}`);
}

export function isBiCardId(value: unknown): value is BiCardId {
  return typeof value === 'string' && CARD_IDS.some((cardId) => cardId === value);
}
