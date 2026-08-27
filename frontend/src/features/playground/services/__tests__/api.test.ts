import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, pipelineApi } from '../api';
import type { WorkflowRun } from '../../types';

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

  it('delivers CRLF SSE progress before the response stream closes', async () => {
    let streamController: ReadableStreamDefaultController<Uint8Array> | undefined;
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        streamController = controller;
      },
    });
    vi.stubGlobal('fetch', vi.fn(async () => new Response(body, {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
    })));
    const events: string[] = [];
    const streamPromise = pipelineApi.streamRun(
      'run-1',
      (event) => events.push(event.event),
    );
    const encoder = new TextEncoder();

    streamController?.enqueue(encoder.encode(
      'event: node_started\r\ndata: {"node_id":"query","status":"running"}\r\n\r\n'
    ));
    await vi.waitFor(() => expect(events).toEqual(['node_started']));

    const completedRun = { id: 'run-1', status: 'completed' } as unknown as WorkflowRun;
    streamController?.enqueue(encoder.encode(
      `event: run_finished\r\ndata: ${JSON.stringify({ run: completedRun })}\r\n\r\n`
    ));
    streamController?.close();

    await expect(streamPromise).resolves.toEqual(completedRun);
    expect(events).toEqual(['node_started', 'run_finished']);
  });
});
