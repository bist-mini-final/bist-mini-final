import type { Edge, Node } from '@xyflow/react';
import { describe, expect, it } from 'vitest';
import {
  applyWorkflowRunToEdges,
  applyWorkflowRunToNodes,
  clearWorkflowExecutionEdges,
  clearWorkflowExecutionNodes,
  deactivateConnectedEdges,
  resumeWorkflowExecutionNodes,
  stopWorkflowExecutionNodes,
} from '../pipelineGraphRuntime';
import type { WorkflowGraph, WorkflowRun } from '../../types';

const graph: WorkflowGraph = {
  nodes: [
    { id: 'source', module_type: 'router', position: { x: 0, y: 0 }, config: {} },
    { id: 'target', module_type: 'reader', position: { x: 100, y: 0 }, config: {} },
  ],
  edges: [{ id: 'edge', source: 'source', target: 'target', source_branch: 'generated' }],
  viewport: { x: 0, y: 0, zoom: 1 },
};

const run: WorkflowRun = {
  schema_version: 1,
  id: 'run-1',
  workflow_id: 'rag-query',
  workflow_updated_at: '2026-08-30T00:00:00Z',
  status: 'running',
  created_at: '2026-08-30T00:00:00Z',
  updated_at: '2026-08-30T00:00:01Z',
  graph,
  runtime_inputs: {},
  use_cache: true,
  batches: [],
  nodes: {
    source: {
      node_id: 'source', module_type: 'router', batch_index: 0, status: 'succeeded',
      input_payload: { query: 'IBM' }, config_payload: { model: 'luna' }, output: { route: true },
      error: null, cache_key: 'source-key', cache_hit: true, outcome: 'generated',
      skip_reason: null, started_at: null, completed_at: null, elapsed_ms: 40, cost_usd: 0.01,
      usage: { total_tokens: 10 },
    },
    target: {
      node_id: 'target', module_type: 'reader', batch_index: 1, status: 'running',
      input_payload: { context: true }, config_payload: {}, output: null, error: null,
      cache_key: null, cache_hit: false, outcome: null, skip_reason: null,
      started_at: null, completed_at: null,
    },
  },
};

const nodes: Node[] = graph.nodes.map((node) => ({
  id: node.id,
  position: node.position,
  data: { executionState: 'pending', marker: node.id },
}));
const edges: Edge[] = [{
  id: 'edge',
  source: 'source',
  target: 'target',
  data: { source_branch: 'generated', active: false, done: false },
}];

describe('pipeline graph runtime state', () => {
  it('maps backend node state and animates the matching running edge', () => {
    const nextNodes = applyWorkflowRunToNodes(nodes, run, new Set());
    const nextEdges = applyWorkflowRunToEdges(edges, run, new Set());

    expect(nextNodes[0].data).toMatchObject({
      executionState: 'succeeded',
      executionOutput: { route: true },
      executionInput: { query: 'IBM' },
      executionConfig: { model: 'luna' },
      cacheHit: true,
      elapsedMs: 40,
    });
    expect(nextEdges[0].data).toMatchObject({ active: true, done: false });
  });

  it('keeps manually stopped descendants idle and clears connected edges', () => {
    const stoppedIds = new Set(['target']);
    const appliedNodes = applyWorkflowRunToNodes(nodes, run, stoppedIds);
    const appliedEdges = applyWorkflowRunToEdges(edges, run, stoppedIds);

    expect(appliedNodes[1].data).toMatchObject({
      executionStopped: true,
      executionState: 'idle',
      executionOutput: null,
    });
    expect(appliedEdges[0].data).toMatchObject({ active: false, done: false });
  });

  it('supports stop, resume, and full execution reset as pure transitions', () => {
    const affected = new Set(['source', 'target']);
    const stopped = stopWorkflowExecutionNodes(nodes, affected);
    const disconnected = deactivateConnectedEdges(
      [{ ...edges[0], data: { ...edges[0].data, active: true } }],
      affected,
    );
    const resumed = resumeWorkflowExecutionNodes(stopped, new Set(['target']));
    const cleared = clearWorkflowExecutionNodes(stopped);

    expect(stopped.every((node) => node.data.executionStopped === true)).toBe(true);
    expect(disconnected[0].data?.active).toBe(false);
    expect(resumed[0].data.executionStopped).toBe(true);
    expect(resumed[1].data.executionStopped).toBe(false);
    expect(cleared.every((node) => node.data.executionStopped === false)).toBe(true);
    expect(clearWorkflowExecutionEdges(disconnected)[0].data)
      .toMatchObject({ active: false, done: false });
  });
});
