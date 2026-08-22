import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  BiApiRequestError,
  createBiMaterialization,
  fetchBiCompanies,
  fetchBiDashboard,
  fetchBiMaterializationJob,
  fetchBiQuestionJob,
  refreshBiDashboard,
} from '../../services/api';

const fetchMock = vi.fn<typeof fetch>();

describe('BI API service', () => {
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => vi.unstubAllGlobals());

  it('parses the company list response', async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ companies: [] }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }));

    const response = await fetchBiCompanies(new AbortController().signal);

    expect(response).toEqual({ companies: [] });
  });

  it('returns a typed pending dashboard result for HTTP 202', async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({
      job: {
        job_id: 'job-1',
        company_id: 'acme',
        workbook_hash: 'a'.repeat(64),
        status: 'extracting',
        completed_requests: 2,
        total_requests: 10,
        published_snapshot_id: null,
        error_code: null,
        message: '추출 중',
        started_at: '2026-08-20T00:00:00Z',
        updated_at: '2026-08-20T00:01:00Z',
      },
    }), {
      status: 202,
      headers: { 'Content-Type': 'application/json' },
    }));

    const result = await fetchBiDashboard('acme', new AbortController().signal);

    expect(result.kind).toBe('pending');
  });

  it('raises a typed request error for a failed response', async () => {
    fetchMock.mockResolvedValue(new Response('{}', {
      status: 404,
      headers: { 'Content-Type': 'application/json' },
    }));

    await expect(fetchBiDashboard('missing', new AbortController().signal))
      .rejects.toBeInstanceOf(BiApiRequestError);
  });

  it('starts materialization with validated snapshot lineage', async () => {
    // Given
    fetchMock.mockResolvedValue(new Response(JSON.stringify({
      job_id: 'job-refresh',
      status: 'queued',
      published_snapshot_id: null,
    }), {
      status: 202,
      headers: { 'Content-Type': 'application/json' },
    }));
    const request = {
      companyId: 'acme',
      displayName: 'ACME',
      source: {
        fileName: 'acme.xlsx',
        workbookHash: 'a'.repeat(64),
        indexId: 'index-acme',
      },
    };

    // When
    const result = await createBiMaterialization(
      request,
      new AbortController().signal,
    );

    // Then
    expect(result.jobId).toBe('job-refresh');
    const input = fetchMock.mock.calls[0]?.[0];
    expect(input).toBeInstanceOf(Request);
    if (!(input instanceof Request)) return;
    expect(input.method).toBe('POST');
    expect(new URL(input.url).pathname).toBe('/api/bi/materializations');
    expect(await input.clone().json()).toEqual({
      company_id: 'acme',
      display_name: 'ACME',
      source: {
        file_name: 'acme.xlsx',
        workbook_hash: 'a'.repeat(64),
        index_id: 'index-acme',
      },
    });
  });

  it('parses a materialization job status response', async () => {
    // Given
    fetchMock.mockResolvedValue(new Response(JSON.stringify({
      job_id: 'job-refresh',
      company_id: 'acme',
      workbook_hash: 'a'.repeat(64),
      status: 'materializing',
      completed_requests: 8,
      total_requests: 10,
      published_snapshot_id: null,
      error_code: null,
      message: '스냅샷 생성 중',
      started_at: '2026-08-20T00:00:00Z',
      updated_at: '2026-08-20T00:01:00Z',
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }));

    // When
    const result = await fetchBiMaterializationJob(
      'job-refresh',
      new AbortController().signal,
    );

    // Then
    expect(result.status).toBe('materializing');
  });

  it('queues and reads a single-question dashboard refresh job', async () => {
    const progress = {
      job_id: 'question-job-refresh',
      total_questions: 26,
      queued_questions: 25,
      running_questions: 1,
      completed_questions: 0,
      failed_questions: 0,
    };
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify(progress), {
        status: 202,
        headers: { 'Content-Type': 'application/json' },
      }))
      .mockResolvedValueOnce(new Response(JSON.stringify(progress), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }));

    const signal = new AbortController().signal;
    const queued = await refreshBiDashboard('acme', signal);
    const current = await fetchBiQuestionJob(queued.jobId, signal);

    expect(queued.totalQuestions).toBe(26);
    expect(current.runningQuestions).toBe(1);
    const first = fetchMock.mock.calls[0]?.[0];
    const second = fetchMock.mock.calls[1]?.[0];
    expect(first).toBeInstanceOf(Request);
    expect(second).toBeInstanceOf(Request);
    if (!(first instanceof Request) || !(second instanceof Request)) return;
    expect(first.method).toBe('POST');
    expect(new URL(first.url).pathname).toBe('/api/bi/companies/acme/refresh');
    expect(new URL(second.url).pathname).toBe(
      '/api/bi/question-jobs/question-job-refresh',
    );
  });
});
