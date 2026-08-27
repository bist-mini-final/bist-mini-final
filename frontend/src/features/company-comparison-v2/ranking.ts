import type { FinancialTier, LeagueCompany } from './leagueTypes';

export interface RankingWeights {
  readonly growth: number;
  readonly profitability: number;
  readonly stability: number;
}

export type RankingPreset = 'balanced' | 'growth' | 'profitability' | 'stability';

export const RANKING_PRESETS: Readonly<Record<RankingPreset, { readonly label: string; readonly weights: RankingWeights }>> = {
  balanced: { label: '종합 균형', weights: { growth: 35, profitability: 35, stability: 30 } },
  growth: { label: '성장 중심', weights: { growth: 60, profitability: 25, stability: 15 } },
  profitability: { label: '수익 중심', weights: { growth: 20, profitability: 60, stability: 20 } },
  stability: { label: '안정 중심', weights: { growth: 20, profitability: 20, stability: 60 } },
};

export function normalizedWeights(weights: RankingWeights): RankingWeights {
  const total = weights.growth + weights.profitability + weights.stability;
  if (total <= 0) return RANKING_PRESETS.balanced.weights;
  return {
    growth: weights.growth / total * 100,
    profitability: weights.profitability / total * 100,
    stability: weights.stability / total * 100,
  };
}

function tierOf(score: number): FinancialTier {
  return score >= 90 ? 'S' : score >= 75 ? 'A' : score >= 60 ? 'B' : 'C';
}

export function rankCompanies(companies: readonly LeagueCompany[], weights: RankingWeights): readonly LeagueCompany[] {
  const normalized = normalizedWeights(weights);
  return companies.map((company) => ({
    company,
    score: (
      company.growthScore * normalized.growth
      + company.profitabilityScore * normalized.profitability
      + company.stabilityScore * normalized.stability
    ) / 100,
  })).sort((left, right) => right.score - left.score).map(({ company, score }, index) => {
    const rank = index + 1;
    const roundedScore = Math.round(score * 100) / 100;
    return {
      ...company,
      rank,
      rankChange: company.previousRank - rank,
      compositeScore: roundedScore,
      tier: tierOf(roundedScore),
    };
  });
}
