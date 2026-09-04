import { Badge, Crown, Gem, ShieldCheck, type LucideIcon } from 'lucide-react';
import type { FinancialTier } from './types';

const TIER_ICONS: Readonly<Record<FinancialTier, LucideIcon>> = {
  S: Crown,
  A: Gem,
  B: ShieldCheck,
  C: Badge,
};

interface FinancialTierBadgeProps {
  readonly tier: FinancialTier;
  readonly compact?: boolean;
}

/** Icon-led financial tier badge; the letter remains available as a compact key. */
export function FinancialTierBadge({ tier, compact = false }: FinancialTierBadgeProps) {
  const Icon = TIER_ICONS[tier];
  return (
    <span
      className={`financial-tier-badge tier-${tier.toLowerCase()}${compact ? ' is-compact' : ''}`}
      aria-label={`${tier} 등급`}
      title={`${tier} 등급`}
    >
      <Icon aria-hidden="true" />
      <b>{tier}</b>
    </span>
  );
}
