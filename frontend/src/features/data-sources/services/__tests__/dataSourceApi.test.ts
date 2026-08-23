import { afterEach, describe, expect, it, vi } from 'vitest';
import { dataSourceApi } from '../dataSourceApi';

describe('dataSourceApi', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('surfaces the message from the current structured API error envelope', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({
        detail: {
          code: 'WORKFLOW_QUEUE_UNAVAILABLE',
          message: 'Kubernetes 실행 큐를 사용할 수 없습니다',
          retryable: true,
          context: {},
        },
      }),
      { status: 503, headers: { 'Content-Type': 'application/json' } },
    )));

    await expect(dataSourceApi.getDbStatus()).rejects.toMatchObject({
      message: 'Kubernetes 실행 큐를 사용할 수 없습니다',
      status: 503,
    });
  });

  it('uses the low-cost embedding model for uploads unless explicitly overridden', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(
      JSON.stringify({}),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));
    vi.stubGlobal('fetch', fetchMock);

    await dataSourceApi.uploadFile(new File(['sheet'], 'sample.xlsx'));

    expect(fetchMock).toHaveBeenCalledOnce();
    const request = fetchMock.mock.calls[0]?.[0];
    expect(request).toBeInstanceOf(Request);
    expect(request instanceof Request ? request.url : '').toContain(
      'model=text-embedding-3-small',
    );
  });
});
