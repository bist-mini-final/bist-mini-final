export const CHART_COLORS = {
  primary: 'var(--bi-chart-primary)',
  secondary: 'var(--bi-chart-secondary)',
  neutral: 'var(--bi-chart-neutral)',
  outflow: 'var(--bi-chart-outflow)',
  grid: 'var(--bi-chart-grid)',
  surface: 'var(--surface)',
} as const;

export const CHART_GEOMETRY = {
  barSize: 16,
  lineWidth: 2,
  dotRadius: 3,
  activeDotRadius: 5,
  margin: { top: 12, right: 8, bottom: 10, left: 0 },
} as const;
