import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  BiApiRequestError,
  createBiMaterialization,
  fetchBiCompanies,
  fetchBiDashboard,
  fetchBiMaterializationCandidates,
  fetchBiMaterializationJob,
  fetchBiQuestionJob,
  refreshBiDashboard,
  resetBiDashboard,
  streamBiMaterializationJob,
} from '../../services/api';

const fetchMock = vi.fn<typeof fetch>();

const dashboardPayload = {
  schema_version: 1,
  company: { company_id: 'acme', display_name: 'ACME' },
  source: {
    file_name: 'acme.xlsx',
    workbook_hash: 'a'.repeat(64),
    index_id: 'index-acme',
  },
  snapshot: {
    snapshot_id: 'snapshot-recalculated',
    workbook_hash: 'a'.repeat(64),
    status: 'ready',
    generated_at: '2026-08-25T00:00:00Z',
    catalog_version: '2',
    formula_version: '2',
  },
  refresh: {
    status: 'idle',
    job_id: 'recalculation-test',
    started_at: null,
    message: null,
  },
  periods: [{
    period_id: 'fy-2025',
    kind: 'fy',
    label: 'FY2025',
    source_label: 'FY2025',
    end_date: '2025-12-31',
    ordinal: 2025,
  }],
  metrics: {},
  issues: [],
};

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

  it('loads snapshot generation candidates from the dedicated endpoint', async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({
      candidates: [{
        company_id: 'acme',
        display_name: 'ACME',
        source: {
          file_name: 'acme.xlsx',
          workbook_hash: 'a'.repeat(64),
          index_id: 'index-acme',
        },
        reason: 'not_created',
      }],
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }));

    const response = await fetchBiMaterializationCandidates(new AbortController().signal);

    expect(response.candidates[0]?.reason).toBe('not_created');
    const input = fetchMock.mock.calls[0]?.[0];
    expect(input).toBeInstanceOf(Request);
    if (input instanceof Request) {
      expect(new URL(input.url).pathname).toBe('/api/v1/bi/materialization-candidates');
    }
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
    expect(new URL(input.url).pathname).toBe('/api/v1/bi/materializations');
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

  it('delivers BI materialization progress before the SSE response closes', async () => {
    let streamController: ReadableStreamDefaultController<Uint8Array> | undefined;
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        streamController = controller;
      },
    });
    fetchMock.mockResolvedValue(new Response(body, {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
    }));
    const statuses: string[] = [];
    const stream = streamBiMaterializationJob(
      'job-live',
      (job) => statuses.push(job.status),
      new AbortController().signal,
    );
    const encoder = new TextEncoder();
    const payload = (status: 'extracting' | 'ready') => ({
      job_id: 'job-live',
      company_id: 'acme',
      workbook_hash: 'a'.repeat(64),
      status,
      completed_requests: status === 'ready' ? 10 : 4,
      total_requests: 10,
      published_snapshot_id: status === 'ready' ? 'snapshot-live' : null,
      error_code: null,
      message: status === 'ready' ? null : '처리 중',
      started_at: '2026-08-20T00:00:00Z',
      updated_at: '2026-08-20T00:01:00Z',
    });

    streamController?.enqueue(encoder.encode(
      `event: materialization_progress\r\ndata: ${JSON.stringify(payload('extracting'))}\r\n\r\n`,
    ));
    await vi.waitFor(() => expect(statuses).toEqual(['extracting']));
    streamController?.enqueue(encoder.encode(
      `event: materialization_completed\r\ndata: ${JSON.stringify(payload('ready'))}\r\n\r\n`,
    ));
    streamController?.close();

    await expect(stream).resolves.toMatchObject({ status: 'ready' });
    expect(statuses).toEqual(['extracting', 'ready']);
  });

  it('recalculates a dashboard without queueing a question job', async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify(dashboardPayload), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }));

    const result = await refreshBiDashboard(
      'acme',
      new AbortController().signal,
    );

    expect(result.snapshot.snapshotId).toBe('snapshot-recalculated');
    const request = fetchMock.mock.calls[0]?.[0];
    expect(request).toBeInstanceOf(Request);
    if (!(request instanceof Request)) return;
    expect(request.method).toBe('POST');
    expect(new URL(request.url).pathname).toBe('/api/v1/bi/companies/acme/refresh');
  });

  it('resets and reads a question regeneration job', async () => {
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
    const queued = await resetBiDashboard('acme', signal);
    const current = await fetchBiQuestionJob(queued.jobId, signal);

    expect(queued.totalQuestions).toBe(26);
    expect(current.runningQuestions).toBe(1);
    const first = fetchMock.mock.calls[0]?.[0];
    const second = fetchMock.mock.calls[1]?.[0];
    expect(first).toBeInstanceOf(Request);
    expect(second).toBeInstanceOf(Request);
    if (!(first instanceof Request) || !(second instanceof Request)) return;
    expect(first.method).toBe('POST');
    expect(new URL(first.url).pathname).toBe('/api/v1/bi/companies/acme/reset');
    expect(new URL(second.url).pathname).toBe(
      '/api/v1/bi/question-jobs/question-job-refresh',
    );
  });
});
