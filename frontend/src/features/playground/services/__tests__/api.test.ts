import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, pipelineApi } from '../api';

describe('playground API errors', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('preserves the structured Kubernetes queue failure contract', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(
      JSON.stringify({
        detail: {
          code: 'WORKFLOW_QUEUE_UNAVAILABLE',
          message: 'Kubernetes queue is unavailable',
          retryable: true,
          context: { workflow_id: 'rag_query' },
        },
      }),
      {
        status: 503,
        headers: { 'Content-Type': 'application/json' },
      },
    )));

    const error = await pipelineApi.createRun('rag_query', {}).catch(
      (caught: unknown) => caught,
    );

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 503,
      code: 'WORKFLOW_QUEUE_UNAVAILABLE',
      message: 'Kubernetes queue is unavailable',
      retryable: true,
      context: { workflow_id: 'rag_query' },
    });
  });
});
