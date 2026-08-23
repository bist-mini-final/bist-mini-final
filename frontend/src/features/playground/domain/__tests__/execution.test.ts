import { describe, expect, it } from 'vitest';
import {
  executionDefinitionFingerprint,
  executionRunMatchesRequest,
  mergeRunNodeUpdate,
  persistentNodeValues,
  runtimeQueryFromRun,
  workflowRuntimeInputs,
} from '../execution';
import type { WorkflowGraph, WorkflowRun } from '../../types';

const graph: WorkflowGraph = {
  nodes: [
    {
      id: 'query',
      module_type: 'query_input',
      position: { x: 0, y: 0 },
      config: {},
      values: {},
    },
    {
      id: 'reader',
      module_type: 'reader',
      position: { x: 200, y: 0 },
      config: { model: 'gpt-5.6-luna' },
      values: {},
    },
  ],
  edges: [{ id: 'answer', source: 'query', target: 'reader' }],
  viewport: { x: 0, y: 0, zoom: 1 },
};

function run(overrides: Partial<WorkflowRun> = {}): WorkflowRun {
  return {
    schema_version: 1,
    id: 'run-1',
    workflow_id: 'rag_query',
    workflow_updated_at: '2026-08-23T00:00:00Z',
    status: 'completed',
    created_at: '2026-08-23T00:00:00Z',
    updated_at: '2026-08-23T00:00:01Z',
    graph,
    runtime_inputs: workflowRuntimeInputs(graph, 'IBM revenue?'),
    use_cache: true,
    batches: [],
    nodes: {},
    ...overrides,
  };
}

describe('workflow execution domain', () => {
  it('keeps runtime query text out of persisted definition values', () => {
    expect(persistentNodeValues('query_input', { query: 'IBM revenue?', locale: 'ko' }))
      .toEqual({ locale: 'ko' });
    expect(persistentNodeValues('reader', { query: 'kept' }))
      .toEqual({ query: 'kept' });
  });

  it('matches the same execution definition regardless of runtime query and ordering', () => {
    const currentGraph: WorkflowGraph = {
      ...graph,
      nodes: [
        { ...graph.nodes[1], config: { model: 'gpt-5.6-luna' } },
        { ...graph.nodes[0], values: { query: 'IBM revenue?' } },
      ],
      edges: [...graph.edges].reverse(),
    };

    expect(executionDefinitionFingerprint(currentGraph))
      .toBe(executionDefinitionFingerprint(graph));
    expect(executionRunMatchesRequest(run(), currentGraph, 'IBM revenue?')).toBe(true);
    expect(executionRunMatchesRequest(run(), currentGraph, 'Different question')).toBe(false);
  });

  it('restores the query from existing run inputs without another request', () => {
    expect(runtimeQueryFromRun(run())).toBe('IBM revenue?');
  });

  it('derives live batch progress from node SSE updates locally', () => {
    const pendingRun = run({
      status: 'queued',
      batches: [
        { index: 0, node_ids: ['query'], status: 'pending', started_at: null, completed_at: null },
        { index: 1, node_ids: ['reader'], status: 'pending', started_at: null, completed_at: null },
      ],
      nodes: {
        query: {
          node_id: 'query', module_type: 'query_input', batch_index: 0, status: 'pending',
          input_payload: null, config_payload: {}, output: null, error: null, cache_key: null,
          cache_hit: false, outcome: null, skip_reason: null, started_at: null, completed_at: null,
        },
        reader: {
          node_id: 'reader', module_type: 'reader', batch_index: 1, status: 'pending',
          input_payload: null, config_payload: {}, output: null, error: null, cache_key: null,
          cache_hit: false, outcome: null, skip_reason: null, started_at: null, completed_at: null,
        },
      },
    });

    const running = mergeRunNodeUpdate(pendingRun, { node_id: 'query', status: 'running' });
    expect(running.status).toBe('running');
    expect(running.batches.map((batch) => batch.status)).toEqual(['running', 'pending']);

    const firstCompleted = mergeRunNodeUpdate(running, { node_id: 'query', status: 'succeeded' });
    expect(firstCompleted.batches.map((batch) => batch.status)).toEqual(['completed', 'pending']);
  });
});
