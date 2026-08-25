import type { BiPeriod, MetricObservation, MetricSeries, PeriodRange } from '../types';

const RANGE_LIMIT: Readonly<Record<PeriodRange, number | null>> = {
  '최근 3개': 3,
  '최근 5개': 5,
  '전체': null,
};

export function selectPeriods(periods: readonly BiPeriod[], range: PeriodRange): readonly BiPeriod[] {
  const sorted = [...periods].sort((left, right) => left.ordinal - right.ordinal);
  const ltmPeriod = [...sorted].reverse().find((period) => period.kind === 'ltm');
  const historicalFy = ltmPeriod
    ? sorted.filter(
      (period) =>
        period.kind === 'fy'
        && (period.endDate != null && ltmPeriod.endDate != null
          ? period.endDate <= ltmPeriod.endDate
          : period.ordinal <= ltmPeriod.ordinal),
    )
    : sorted.filter((period) => period.kind === 'fy');
  const futureFy = ltmPeriod
    ? sorted.filter(
      (period) =>
        period.kind === 'fy'
        && (period.endDate != null && ltmPeriod.endDate != null
          ? period.endDate > ltmPeriod.endDate
          : period.ordinal > ltmPeriod.ordinal),
    )
    : [];
  const limit = RANGE_LIMIT[range];
  if (limit === null) {
    return ltmPeriod ? [...historicalFy, ltmPeriod, ...futureFy] : sorted;
  }
  const selectedFy = historicalFy.slice(-limit);
  return ltmPeriod ? [...selectedFy, ltmPeriod] : selectedFy;
}

export function selectObservations(
  series: MetricSeries,
  periods: readonly BiPeriod[],
): readonly MetricObservation[] {
  const observationsByPeriod = new Map(series.observations.map((observation) => [observation.periodId, observation]));
  const selected = periods.flatMap((period) => {
    const observation = observationsByPeriod.get(period.periodId);
    return observation ? [{ period, observation }] : [];
  });
  const ltm = [...selected].reverse().find((item) => item.period.kind === 'ltm');
  if (!ltm || ltm.observation.status !== 'available') return selected.map((item) => item.observation);

  return selected
    .filter((item) => {
      if (item.period.kind !== 'fy' || item.period.endDate !== ltm.period.endDate) return true;
      return item.observation.status !== 'available'
        || item.observation.normalizedValue !== ltm.observation.normalizedValue;
    })
    .map((item) => item.observation);
}

export function selectRepresentativeObservation(
  series: MetricSeries,
  periods: readonly BiPeriod[],
): MetricObservation | null {
  const observations = selectObservations(series, periods);
  const availableInRange = observations.filter(
    (observation) => observation.status === 'available',
  );
  if (availableInRange.length > 0) {
    return availableInRange[availableInRange.length - 1];
  }
  const allAvailable = series.observations.filter(
    (observation) => observation.status === 'available',
  );
  if (allAvailable.length > 0) {
    return allAvailable[allAvailable.length - 1];
  }
  return observations[observations.length - 1] ?? null;
}

