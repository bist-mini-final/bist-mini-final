import { describe, it, expect } from 'vitest';
import { formatMetricValue } from '../formatMetric';
import { formatChartAxis, formatChartValue } from '../chartViewModel';
import { selectPeriods, selectObservations, selectRepresentativeObservation } from '../periods';
import { buildCardViewModel } from '../cardViewModel';
import { getCardDefinition, CARD_REGISTRY } from '../../config/cardRegistry';
import { DASHBOARD_FIXTURES } from '../../../../test/fixtures/biDashboardFixtures';
import type { BiPeriod, MetricObservation, MetricSeries } from '../../types';

describe('BI Selectors & ViewModel', () => {
  const mockSeries: MetricSeries = {
    metricId: 'revenue',
    label: '매출액',
    valueKind: 'amount',
    currency: 'KRW',
    scale: 'millions',
    status: 'available',
    observations: [
      {
        periodId: 'fy2021',
        rawValue: '1000',
        normalizedValue: '1000',
        status: 'available',
        evidence: [{ cellId: 'c1', sheetName: 'IS', cellCoord: 'B5', sourceText: '매출: 1000' }],
        notes: [],
      },
      {
        periodId: 'fy2022',
        rawValue: '150000',
        normalizedValue: '150000',
        status: 'available',
        evidence: [],
        notes: [],
      },
      {
        periodId: 'fy2023',
        rawValue: '2500000',
        normalizedValue: '2500000',
        status: 'available',
        evidence: [],
        notes: [],
      },
    ],
  };

  describe('formatMetricValue', () => {
    it('formats amounts in millions, hundred millions (억원), and trillions (조원)', () => {
      const obsMillions: MetricObservation = {
        periodId: 'p1',
        rawValue: '50',
        normalizedValue: '50',
        status: 'available',
        evidence: [],
        notes: [],
      };
      expect(formatMetricValue(mockSeries, obsMillions)).toBe('50백만원');

      const obsEok: MetricObservation = {
        periodId: 'p2',
        rawValue: '150000',
        normalizedValue: '150000',
        status: 'available',
        evidence: [],
        notes: [],
      };
      expect(formatMetricValue(mockSeries, obsEok)).toBe('1,500억원');

      const obsTrillion: MetricObservation = {
        periodId: 'p3',
        rawValue: '2500000',
        normalizedValue: '2500000',
        status: 'available',
        evidence: [],
        notes: [],
      };
      expect(formatMetricValue(mockSeries, obsTrillion)).toBe('2.5조원');
    });

    it('formats percentages correctly', () => {
      const percentSeries: MetricSeries = {
        ...mockSeries,
        metricId: 'operating_margin',
        valueKind: 'percent',
      };
      const obs: MetricObservation = {
        periodId: 'p1',
        rawValue: '15.4',
        normalizedValue: '15.4',
        status: 'available',
        evidence: [],
        notes: [],
      };
      expect(formatMetricValue(percentSeries, obs)).toBe('+15.4%');
    });

    it('handles non-available statuses gracefully', () => {
      expect(formatMetricValue(mockSeries, null)).toBe('데이터 없음');

      const missingObs: MetricObservation = {
        periodId: 'p1',
        rawValue: null,
        normalizedValue: null,
        status: 'missing',
        reason: 'Not found',
        evidence: [],
        notes: [],
      };
      expect(formatMetricValue(mockSeries, missingObs)).toBe('데이터 없음');

      const ambiguousObs: MetricObservation = {
        periodId: 'p2',
        rawValue: null,
        normalizedValue: null,
        status: 'ambiguous',
        reason: 'Multiple cells match',
        evidence: [],
        notes: [],
      };
      expect(formatMetricValue(mockSeries, ambiguousObs)).toBe('확인 필요');

      expect(formatMetricValue(mockSeries, {
        ...ambiguousObs,
        rawValue: '120',
      })).toBe('120 (단위 확인 필요)');
    });
  });

  describe('selectPeriods', () => {
    const mockPeriods: readonly BiPeriod[] = [
      { periodId: 'fy2019', kind: 'fy', label: '2019', sourceLabel: '2019', endDate: '2019-12-31', ordinal: 1 },
      { periodId: 'fy2020', kind: 'fy', label: '2020', sourceLabel: '2020', endDate: '2020-12-31', ordinal: 2 },
      { periodId: 'fy2021', kind: 'fy', label: '2021', sourceLabel: '2021', endDate: '2021-12-31', ordinal: 3 },
      { periodId: 'fy2022', kind: 'fy', label: '2022', sourceLabel: '2022', endDate: '2022-12-31', ordinal: 4 },
      { periodId: 'fy2023', kind: 'fy', label: '2023', sourceLabel: '2023', endDate: '2023-12-31', ordinal: 5 },
      { periodId: 'ltm', kind: 'ltm', label: 'LTM', sourceLabel: 'LTM', endDate: '2024-06-30', ordinal: 6 },
    ];

    it('filters periods by recent 3, recent 5, and all ranges', () => {
      const recent3 = selectPeriods(mockPeriods, '최근 3개');
      expect(recent3.map((p) => p.periodId)).toEqual(['fy2021', 'fy2022', 'fy2023', 'ltm']);

      const recent5 = selectPeriods(mockPeriods, '최근 5개');
      expect(recent5.map((p) => p.periodId)).toEqual(['fy2019', 'fy2020', 'fy2021', 'fy2022', 'fy2023', 'ltm']);

      const all = selectPeriods(mockPeriods, '전체');
      expect(all.length).toBe(6);
    });

    it('formats USD millions without converting them to KRW hundred-millions', () => {
      const usdSeries: MetricSeries = {
        ...mockSeries,
        currency: 'USD',
        scale: 'millions',
      };
      const observation: MetricObservation = {
        periodId: 'fy2025',
        rawValue: '67535',
        normalizedValue: '67535',
        status: 'available',
        evidence: [],
        notes: [],
      };

      expect(formatMetricValue(usdSeries, observation)).toBe('$67,535M');
      expect(formatChartValue(67535, 'amount', usdSeries)).toBe('$67,535M');
      expect(formatChartAxis(127243, 'amount', usdSeries)).toBe('$127,243M');
      expect(formatChartValue(-1600, 'amount', usdSeries)).toBe('-$1,600M');
    });

    it('keeps FY periods when source dates are unavailable', () => {
      const periodsWithMissingDates: readonly BiPeriod[] = [
        { periodId: 'fy2023', kind: 'fy', label: '2023', sourceLabel: '2023', endDate: null, ordinal: 1 },
        { periodId: 'fy2024', kind: 'fy', label: '2024', sourceLabel: '2024', endDate: '2024-12-31', ordinal: 2 },
        { periodId: 'ltm', kind: 'ltm', label: 'LTM', sourceLabel: 'LTM', endDate: null, ordinal: 3 },
      ];

      expect(selectPeriods(periodsWithMissingDates, '전체').map((period) => period.periodId))
        .toEqual(['fy2023', 'fy2024', 'ltm']);
    });

    it('selects observations and representative observation', () => {
      const observations = selectObservations(mockSeries, mockPeriods);
      expect(observations.length).toBeGreaterThan(0);

      const representative = selectRepresentativeObservation(mockSeries, mockPeriods);
      expect(representative).toBeDefined();
      expect(representative?.normalizedValue).toBe('2500000');
    });
  });

  describe('buildCardViewModel with fixtures', () => {
    const spgDashboard = DASHBOARD_FIXTURES[0];

    it('builds valid view models for all registered cards', () => {
      CARD_REGISTRY.forEach((cardDef) => {
        const vm = buildCardViewModel({
          definition: cardDef,
          dashboard: spgDashboard,
          range: '최근 5개',
          size: 'M',
        });

        expect(vm.state).toBeDefined();
        expect(vm.primaryLabel).toBeTruthy();
        expect(vm.primaryValue).toBeTruthy();
        expect(Array.isArray(vm.rows)).toBe(true);
        expect(Array.isArray(vm.evidence)).toBe(true);
      });
    });

    it('extracts primary and secondary metrics for revenue growth card', () => {
      const revDef = getCardDefinition('revenue_growth');
      expect(revDef).toBeDefined();

      if (revDef) {
        const vm = buildCardViewModel({
          definition: revDef,
          dashboard: spgDashboard,
          range: '최근 5개',
          size: 'L',
        });

        expect(vm.state).toBe('ready');
        expect(vm.primaryLabel).toBe('매출');
        expect(vm.secondaryLabel).toBe('매출 성장률');
        expect(vm.rows.length).toBeGreaterThan(0);
      }
    });
  });
});
