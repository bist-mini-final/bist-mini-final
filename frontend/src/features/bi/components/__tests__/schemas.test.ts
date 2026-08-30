import { describe, expect, it } from 'vitest';
import {
  parseBiCompanies,
  parseBiDashboard,
  parseBiMaterializationCandidates,
} from '../../schemas';

describe('BI API schemas', () => {
  it('maps materialization candidates and their generation reason', () => {
    const response = parseBiMaterializationCandidates({
      candidates: [{
        company_id: 'acme',
        display_name: 'ACME',
        source: {
          file_name: 'acme.xlsx',
          workbook_hash: 'a'.repeat(64),
          index_id: 'index-acme',
        },
        reason: 'source_changed',
      }],
    });

    expect(response.candidates[0]).toEqual({
      companyId: 'acme',
      displayName: 'ACME',
      source: {
        fileName: 'acme.xlsx',
        workbookHash: 'a'.repeat(64),
        indexId: 'index-acme',
      },
      reason: 'source_changed',
    });
  });

  it('maps the company list contract to readonly frontend fields', () => {
    const response = parseBiCompanies({
      companies: [{
        company_id: 'acme',
        display_name: 'ACME',
        source: {
          file_name: 'acme.xlsx',
          workbook_hash: 'a'.repeat(64),
          index_id: 'index-acme',
        },
        current_snapshot_id: 'snapshot-1',
        snapshot_status: 'ready',
        refresh_status: 'idle',
        updated_at: '2026-08-20T00:00:00Z',
      }],
    });

    expect(response.companies[0]).toEqual({
      companyId: 'acme',
      displayName: 'ACME',
      source: {
        fileName: 'acme.xlsx',
        workbookHash: 'a'.repeat(64),
        indexId: 'index-acme',
      },
      currentSnapshotId: 'snapshot-1',
      snapshotStatus: 'ready',
      refreshStatus: 'idle',
      updatedAt: '2026-08-20T00:00:00Z',
    });
  });

  it('preserves missing metric values as null', () => {
    const dashboard = parseBiDashboard({
      schema_version: 1,
      company: { company_id: 'acme', display_name: 'ACME' },
      source: {
        file_name: 'acme.xlsx',
        workbook_hash: 'a'.repeat(64),
        index_id: 'index-acme',
      },
      snapshot: {
        snapshot_id: 'snapshot-1',
        workbook_hash: 'a'.repeat(64),
        status: 'partial',
        generated_at: '2026-08-20T00:00:00Z',
        catalog_version: 'v1',
        formula_version: 'v1',
      },
      refresh: { status: 'idle', job_id: null, started_at: null, message: null },
      periods: [{
        period_id: 'fy-2025',
        kind: 'fy',
        label: 'FY2025',
        source_label: 'FY0',
        end_date: '2025-12-31',
        ordinal: 1,
      }],
      metrics: {
        revenue: {
          metric_id: 'revenue',
          label: '매출',
          value_kind: 'amount',
          currency: 'KRW',
          scale: 'millions',
          status: 'missing',
          observations: [{
            period_id: 'fy-2025',
            status: 'missing',
            raw_value: 'NA',
            normalized_value: null,
            evidence: [],
            notes: [],
            reason: 'source_value_missing',
          }],
        },
      },
      issues: [{ code: 'metric.missing', message: '값 없음', metric_id: 'revenue' }],
    });

    expect(dashboard.metrics.revenue?.observations[0]?.normalizedValue).toBeNull();
    expect(dashboard.metrics.revenue?.observations[0]?.rawValue).toBe('NA');
    expect(dashboard.source.fileName).toBe('acme.xlsx');
  });

  it('keeps an available metric when optional evidence is empty', () => {
    const dashboard = parseBiDashboard({
      schema_version: 1,
      company: { company_id: 'acme', display_name: 'ACME' },
      source: {
        file_name: 'acme.xlsx',
        workbook_hash: 'a'.repeat(64),
        index_id: 'index-acme',
      },
      snapshot: {
        snapshot_id: 'snapshot-1',
        workbook_hash: 'a'.repeat(64),
        status: 'ready',
        generated_at: '2026-08-20T00:00:00Z',
        catalog_version: 'v1',
        formula_version: 'v1',
      },
      refresh: { status: 'idle', job_id: null, started_at: null, message: null },
      periods: [{
        period_id: 'fy-2025',
        kind: 'fy',
        label: 'FY2025',
        source_label: 'FY0',
        end_date: '2025-12-31',
        ordinal: 0,
      }],
      metrics: {
        revenue: {
          metric_id: 'revenue',
          label: '매출',
          value_kind: 'amount',
          currency: 'USD',
          scale: 'millions',
          status: 'available',
          observations: [{
            period_id: 'fy-2025',
            status: 'available',
            raw_value: '100',
            normalized_value: '100',
            evidence: [],
            notes: [],
          }],
        },
      },
      issues: [],
    });

    expect(dashboard.metrics.revenue?.observations[0]?.normalizedValue).toBe('100');
    expect(dashboard.metrics.revenue?.observations[0]?.evidence).toEqual([]);
  });
});
