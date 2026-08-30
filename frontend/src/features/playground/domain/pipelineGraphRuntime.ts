import type { Edge, Node } from '@xyflow/react';
import type { WorkflowRun } from '../types';

function clearedExecutionData(data: Record<string, unknown>) {
  return {
    ...data,
    executionState: undefined,
    executionOutput: null,
    executionInput: null,
    executionError: null,
    executionOutcome: null,
    cacheHit: false,
    batchIndex: undefined,
  };
}

function stoppedExecutionData(data: Record<string, unknown>) {
  return {
    ...clearedExecutionData(data),
    executionStopped: true,
    executionState: 'idle',
  };
}

export function applyWorkflowRunToNodes(
  nodes: readonly Node[],
  run: WorkflowRun,
  stoppedNodeIds: ReadonlySet<string>,
): Node[] {
  return nodes.map((node) => {
    const state = run.nodes[node.id];
    if (!state) return node;
    if (stoppedNodeIds.has(node.id)) {
      return { ...node, data: stoppedExecutionData(node.data) };
    }
    return {
      ...node,
      data: {
        ...node.data,
        executionStopped: false,
        executionState: state.status,
        executionOutput: state.output,
        executionInput: state.input_payload,
        executionConfig: state.config_payload,
        executionError: state.error,
        executionOutcome: state.outcome,
        cacheHit: state.cache_hit,
        batchIndex: state.batch_index,
        elapsedMs: state.elapsed_ms,
        costUsd: state.cost_usd,
        usage: state.usage,
      },
    };
  });
}

export function applyWorkflowRunToEdges(
  edges: readonly Edge[],
  run: WorkflowRun,
  stoppedNodeIds: ReadonlySet<string>,
): Edge[] {
  return edges.map((edge) => {
    if (stoppedNodeIds.has(edge.source) || stoppedNodeIds.has(edge.target)) {
      return { ...edge, data: { ...edge.data, active: false, done: false } };
    }
    const sourceState = run.nodes[edge.source]?.status;
    const sourceOutcome = run.nodes[edge.source]?.outcome;
    const targetState = run.nodes[edge.target]?.status;
    const sourceBranch = edge.data?.source_branch;
    const branchMatches = typeof sourceBranch === 'string'
      ? sourceOutcome === sourceBranch
      : sourceState === 'succeeded';
    return {
      ...edge,
      data: {
        ...edge.data,
        done: branchMatches && targetState === 'succeeded',
        active: branchMatches && targetState === 'running',
      },
    };
  });
}

export function clearWorkflowExecutionNodes(nodes: readonly Node[]): Node[] {
  return nodes.map((node) => ({
    ...node,
    data: { ...clearedExecutionData(node.data), executionStopped: false },
  }));
}

export function clearWorkflowExecutionEdges(edges: readonly Edge[]): Edge[] {
  return edges.map((edge) => ({
    ...edge,
    data: { ...edge.data, active: false, done: false },
  }));
}

export function stopWorkflowExecutionNodes(
  nodes: readonly Node[],
  stoppedNodeIds: ReadonlySet<string>,
): Node[] {
  return nodes.map((node) => stoppedNodeIds.has(node.id)
    ? { ...node, data: stoppedExecutionData(node.data) }
    : node);
}

export function resumeWorkflowExecutionNodes(
  nodes: readonly Node[],
  resumedNodeIds: ReadonlySet<string>,
): Node[] {
  return nodes.map((node) => resumedNodeIds.has(node.id)
    ? { ...node, data: { ...node.data, executionStopped: false } }
    : node);
}

export function deactivateConnectedEdges(
  edges: readonly Edge[],
  affectedNodeIds: ReadonlySet<string>,
): Edge[] {
  return edges.map((edge) => affectedNodeIds.has(edge.source) || affectedNodeIds.has(edge.target)
    ? { ...edge, data: { ...edge.data, active: false, done: false } }
    : edge);
}
