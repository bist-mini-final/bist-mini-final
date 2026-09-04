import type { FinancialTier } from './types';

interface FinancialTierBadgeProps {
  readonly tier: FinancialTier;
  readonly compact?: boolean;
}

/** Color-coded financial tier label without decorative chrome. */
export function FinancialTierBadge({ tier, compact = false }: FinancialTierBadgeProps) {
  return (
    <span
      className={`financial-tier-badge tier-${tier.toLowerCase()}${compact ? ' is-compact' : ''}`}
      aria-label={`${tier} 등급`}
      title={`${tier} 등급`}
    >
      <b>{tier}</b>
    </span>
  );
}
