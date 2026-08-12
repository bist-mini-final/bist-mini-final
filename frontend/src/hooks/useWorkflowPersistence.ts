import { useCallback, useEffect, useRef, useState } from 'react';
import { pipelineApi, ApiError } from '../services/api';
import type {
  SaveStatus,
  WorkflowGraph,
  WorkflowRun,
} from '../types';

const ACTIVE_WORKFLOW_ID = 'workflow';
const ACTIVE_WORKFLOW_NAME = 'Excel RAG Flow';

interface WorkflowGraphBridge {
  exportGraph: () => WorkflowGraph;
  replaceGraph: (graph: WorkflowGraph) => void;
  applyRun: (run: WorkflowRun) => void;
  clearExecutionState: () => void;
}

function runInputs(
  graph: WorkflowGraph,
  query: string
): Record<string, Record<string, unknown>> {
  return Object.fromEntries(
    graph.nodes
      .filter((node) => node.module_type === 'query_input')
      .map((node) => [
        node.id,
        { query },
      ])
  );
}

function executionFingerprint(graph: WorkflowGraph): string {
  return JSON.stringify({
    nodes: (graph.nodes ?? []).map(({ id, module_type, config }) => ({
      id,
      module_type,
      config: config ?? {},
    })),
    edges: (graph.edges ?? []).map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      source_output: edge.source_output ?? null,
      target_input: edge.target_input ?? null,
      source_branch: edge.source_branch ?? null,
    })),
  });
}

/**
 * Returns true when the current graph is compatible with the given run for
 * display purposes.  "Compatible" means every node that already exists in the
 * run still has the same module_type, config, and connected edges — i.e. the
 * user only *added* new nodes/edges without modifying existing ones.
 * New nodes simply have no state in the run and will be shown as idle.
 */
function executionRunCompatibleWithGraph(
  run: WorkflowRun,
  graph: WorkflowGraph
): boolean {
  const currentNodeById = new Map(
    (graph.nodes ?? []).map((n) => [n.id, n])
  );
  const currentEdgeSet = new Set(
    (graph.edges ?? []).map((e) =>
      JSON.stringify([
        e.id,
        e.source,
        e.target,
        e.source_output ?? null,
        e.target_input ?? null,
        e.source_branch ?? null,
      ])
    )
  );

  // Every node present in the run must still exist in the current graph
  // with the same module_type and config.
  for (const runNode of run.graph.nodes) {
    const currentNode = currentNodeById.get(runNode.id);
    if (!currentNode) return false;
    if (currentNode.module_type !== runNode.module_type) return false;
    if (JSON.stringify(currentNode.config ?? {}) !== JSON.stringify(runNode.config ?? {})) return false;
  }

  // Every edge present in the run must still exist in the current graph.
  for (const runEdge of run.graph.edges) {
    const key = JSON.stringify([
      runEdge.id,
      runEdge.source,
      runEdge.target,
      runEdge.source_output ?? null,
      runEdge.target_input ?? null,
      runEdge.source_branch ?? null,
    ]);
    if (!currentEdgeSet.has(key)) return false;
  }

  return true;
}

function markNextBatchRunning(run: WorkflowRun): WorkflowRun {
  const retryingFailure = run.status === 'failed';
  const nextBatch = run.batches.find((batch) =>
    retryingFailure ? batch.status === 'failed' : batch.status === 'pending'
  );
  if (!nextBatch) return run;

  const startedAt = new Date().toISOString();
  const runningNodeIds = new Set(
    retryingFailure
      ? nextBatch.node_ids.filter((nodeId) => run.nodes[nodeId]?.status === 'failed')
      : nextBatch.node_ids
  );
  return {
    ...run,
    status: 'running',
    updated_at: startedAt,
    batches: run.batches.map((batch) =>
      batch.index === nextBatch.index
        ? { ...batch, status: 'running', started_at: startedAt }
        : batch
    ),
    nodes: Object.fromEntries(
      Object.entries(run.nodes).map(([nodeId, node]) => [
        nodeId,
        runningNodeIds.has(nodeId)
          ? {
              ...node,
              status: 'running',
              error: null,
              skip_reason: null,
              started_at: startedAt,
              completed_at: null,
            }
          : node,
      ])
    ),
  };
}

function descendantNodeIds(graph: WorkflowGraph, nodeId: string): Set<string> {
  const outgoing = new Map<string, string[]>();
  graph.edges.forEach((edge) => {
    outgoing.set(edge.source, [...(outgoing.get(edge.source) ?? []), edge.target]);
  });
  const descendants = new Set<string>();
  const pending = [...(outgoing.get(nodeId) ?? [])];
  while (pending.length > 0) {
    const candidate = pending.pop();
    if (!candidate || descendants.has(candidate)) continue;
    descendants.add(candidate);
    pending.push(...(outgoing.get(candidate) ?? []));
  }
  return descendants;
}

function markNodeRunning(run: WorkflowRun, nodeId: string): WorkflowRun {
  const selectedNode = run.nodes[nodeId];
  if (!selectedNode) return run;
  const startedAt = new Date().toISOString();
  const descendants = descendantNodeIds(run.graph, nodeId);
  const resetNodeIds = new Set([nodeId, ...descendants]);
  const nodes = Object.fromEntries(
    Object.entries(run.nodes).map(([candidateId, node]) => {
      if (!resetNodeIds.has(candidateId)) return [candidateId, node];
      if (candidateId === nodeId) {
        return [candidateId, {
          ...node,
          status: 'running',
          input_payload: null,
          output: null,
          error: null,
          cache_key: null,
          cache_hit: false,
          outcome: null,
          skip_reason: null,
          started_at: startedAt,
          completed_at: null,
        }];
      }
      return [candidateId, {
        ...node,
        status: 'pending',
        input_payload: null,
        output: null,
        error: null,
        cache_key: null,
        cache_hit: false,
        outcome: null,
        skip_reason: null,
        started_at: null,
        completed_at: null,
      }];
    })
  ) as WorkflowRun['nodes'];

  return {
    ...run,
    status: 'running',
    updated_at: startedAt,
    nodes,
    batches: run.batches.map((batch) => {
      if (batch.index === selectedNode.batch_index) {
        return {
          ...batch,
          status: 'running',
          started_at: startedAt,
          completed_at: null,
        };
      }
      if (batch.node_ids.some((candidateId) => descendants.has(candidateId))) {
        return {
          ...batch,
          status: 'pending',
          completed_at: null,
        };
      }
      return batch;
    }),
  };
}

async function executeNextOrResume(
  run: WorkflowRun,
  signal: AbortSignal
): Promise<WorkflowRun> {
  if (run.status === 'failed') {
    return pipelineApi.resumeRun(run.id, signal);
  }
  try {
    return await pipelineApi.executeNextBatch(run.id, signal);
  } catch (error) {
    // A stopped browser request does not cancel the synchronous backend worker.
    // Reconcile the persisted run before deciding whether execute-next is valid.
    if (error instanceof ApiError && error.status === 422) {
      const persistedRun = await pipelineApi.getRun(run.id, signal);
      if (persistedRun.status === 'failed') {
        return pipelineApi.resumeRun(run.id, signal);
      }
    }
    throw error;
  }
}

export function useWorkflowPersistence(
  graph: WorkflowGraphBridge,
  moduleCatalogReady: boolean
) {
  const graphRef = useRef(graph);
  graphRef.current = graph;
  const currentGraph = graph.exportGraph();
  const graphFingerprint = JSON.stringify(currentGraph);
  const [ready, setReady] = useState(false);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('loading');
  const [lastSavedAt, setLastSavedAt] = useState<string | null>(null);
  const [latestRun, setLatestRun] = useState<WorkflowRun | null>(null);
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [isExecuting, setIsExecuting] = useState(false);
  const [isClearingCache, setIsClearingCache] = useState(false);
  const executionController = useRef<AbortController | null>(null);
  const stableRunRef = useRef<WorkflowRun | null>(null);
  const runtimeMutationEpoch = useRef(0);
  // Strict match: used to decide whether to reuse an existing run for execution.
  const latestRunMatchesGraph = Boolean(
    latestRun && executionFingerprint(latestRun.graph) === executionFingerprint(currentGraph)
  );
  // Loose compatibility: used to decide whether to keep showing run results in
  // the UI when new nodes have been added but existing ones are unchanged.
  const latestRunCompatibleWithGraph = Boolean(
    latestRun && executionRunCompatibleWithGraph(latestRun, currentGraph)
  );

  const applyRun = useCallback((run: WorkflowRun) => {
    setLatestRun(run);
    setRuns((currentRuns) =>
      [run, ...currentRuns.filter((candidate) => candidate.id !== run.id)]
        .sort((left, right) => right.updated_at.localeCompare(left.updated_at))
    );
    graphRef.current.applyRun(run);
  }, []);

  useEffect(() => {
    if (!moduleCatalogReady) {
      setSaveStatus('loading');
      return;
    }
    const controller = new AbortController();
    const load = async () => {
      setSaveStatus('loading');
      try {
        let workflow;
        try {
          workflow = await pipelineApi.getWorkflow(ACTIVE_WORKFLOW_ID, controller.signal);
          graphRef.current.replaceGraph(workflow.graph);
        } catch (error: unknown) {
          if (!(error instanceof ApiError && error.status === 404)) throw error;
          workflow = await pipelineApi.saveWorkflow(
            ACTIVE_WORKFLOW_ID,
            ACTIVE_WORKFLOW_NAME,
            graphRef.current.exportGraph(),
            controller.signal
          );
        }

        const response = await pipelineApi.getRuns(ACTIVE_WORKFLOW_ID, controller.signal);
        const sortedRuns = response.runs
          .slice()
          .sort((left, right) => right.updated_at.localeCompare(left.updated_at));
        setRuns(sortedRuns);
        const mostRecentRun = sortedRuns[0];
        if (mostRecentRun) applyRun(mostRecentRun);
        setLastSavedAt(workflow.updated_at);
        setSaveStatus('saved');
        setReady(true);
      } catch (error: unknown) {
        if (!(error instanceof DOMException && error.name === 'AbortError')) {
          setSaveStatus('error');
        }
      }
    };
    void load();
    return () => controller.abort();
  }, [applyRun, moduleCatalogReady]);

  const saveNow = useCallback(async (signal?: AbortSignal) => {
    setSaveStatus('saving');
    try {
      const workflow = await pipelineApi.saveWorkflow(
        ACTIVE_WORKFLOW_ID,
        ACTIVE_WORKFLOW_NAME,
        graphRef.current.exportGraph(),
        signal
      );
      setLastSavedAt(workflow.updated_at);
      setSaveStatus('saved');
      return workflow;
    } catch (error) {
      if (!(error instanceof DOMException && error.name === 'AbortError')) {
        setSaveStatus('error');
      }
      throw error;
    }
  }, []);

  useEffect(() => {
    if (!ready) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void saveNow(controller.signal).catch(() => undefined);
    }, 700);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [graphFingerprint, ready, saveNow]);

  const createRun = useCallback(
    async (query: string, signal: AbortSignal, inheritFromRunId?: string) => {
      const workflow = await saveNow(signal);
      const run = await pipelineApi.createRun(
        ACTIVE_WORKFLOW_ID,
        runInputs(workflow.graph, query),
        signal,
        inheritFromRunId
      );
      applyRun(run);
      return run;
    },
    [applyRun, saveNow]
  );

  const executeAll = useCallback(
    async (
      query: string,
      onBatch?: (run: WorkflowRun) => void
    ) => {
      executionController.current?.abort();
      const controller = new AbortController();
      executionController.current = controller;
      setIsExecuting(true);
      try {
        const currentExecutionGraph = graphRef.current.exportGraph();
        let run = latestRun &&
          (latestRun.status === 'queued' ||
            latestRun.status === 'running' ||
            latestRun.status === 'failed') &&
          executionFingerprint(latestRun.graph) === executionFingerprint(currentExecutionGraph)
          ? latestRun
          : await createRun(query, controller.signal);
        applyRun(run);
        onBatch?.(run);
        while (run.status === 'queued' || run.status === 'running') {
          const stableRun = run;
          const runningRun = markNextBatchRunning(run);
          stableRunRef.current = stableRun;
          applyRun(runningRun);
          onBatch?.(runningRun);
          try {
            run = await executeNextOrResume(run, controller.signal);
          } catch (error) {
            if (!controller.signal.aborted) {
              applyRun(stableRun);
              onBatch?.(stableRun);
            }
            throw error;
          } finally {
            if (executionController.current === controller) {
              stableRunRef.current = null;
            }
          }
          applyRun(run);
          onBatch?.(run);
        }
        if (run.status === 'failed') {
          const failure = Object.values(run.nodes).find((node) => node.status === 'failed');
          throw new Error(failure?.error ?? '워크플로 실행에 실패했습니다.');
        }
        return run;
      } finally {
        if (!controller.signal.aborted) setIsExecuting(false);
        if (executionController.current === controller) executionController.current = null;
      }
    },
    [applyRun, createRun, latestRun]
  );

  const executeNext = useCallback(
    async (query: string, onBatch?: (run: WorkflowRun) => void) => {
      executionController.current?.abort();
      const controller = new AbortController();
      executionController.current = controller;
      setIsExecuting(true);
      try {
        const currentExecutionGraph = graphRef.current.exportGraph();
        let run = latestRun &&
          executionFingerprint(latestRun.graph) === executionFingerprint(currentExecutionGraph)
          ? latestRun
          : null;
        if (!run || run.status === 'completed') {
          run = await createRun(query, controller.signal);
        }
        if (run.status === 'queued' || run.status === 'running' || run.status === 'failed') {
          const stableRun = run;
          const runningRun = markNextBatchRunning(run);
          stableRunRef.current = stableRun;
          applyRun(runningRun);
          onBatch?.(runningRun);
          try {
            run = await executeNextOrResume(run, controller.signal);
          } catch (error) {
            if (!controller.signal.aborted) {
              applyRun(stableRun);
              onBatch?.(stableRun);
            }
            throw error;
          } finally {
            if (executionController.current === controller) {
              stableRunRef.current = null;
            }
          }
        }
        applyRun(run);
        onBatch?.(run);
        return run;
      } finally {
        if (!controller.signal.aborted) setIsExecuting(false);
        if (executionController.current === controller) executionController.current = null;
      }
    },
    [applyRun, createRun, latestRun]
  );

  const executeNode = useCallback(
    async (
      nodeId: string,
      query: string,
      onUpdate?: (run: WorkflowRun) => void
    ) => {
      executionController.current?.abort();
      const controller = new AbortController();
      executionController.current = controller;
      setIsExecuting(true);
      try {
        const currentExecutionGraph = graphRef.current.exportGraph();
        const currentRuntimeInputs = runInputs(currentExecutionGraph, query);
        const strictMatch = latestRun
          && executionFingerprint(latestRun.graph) === executionFingerprint(currentExecutionGraph)
          && JSON.stringify(latestRun.runtime_inputs) === JSON.stringify(currentRuntimeInputs);
        const looseMatch = !strictMatch
          && latestRun
          && executionRunCompatibleWithGraph(latestRun, currentExecutionGraph)
          && JSON.stringify(latestRun.runtime_inputs) === JSON.stringify(currentRuntimeInputs);
        let run: WorkflowRun;
        if (strictMatch && latestRun) {
          // Graph unchanged: reuse existing run directly.
          run = latestRun;
        } else if (looseMatch && latestRun) {
          // Only new nodes added: create a new run but inherit completed states
          // from the previous run so upstream nodes are seen as 'succeeded'.
          run = await createRun(query, controller.signal, latestRun.id);
        } else {
          run = await createRun(query, controller.signal);
        }

        const stableRun = run;
        const runningRun = markNodeRunning(run, nodeId);
        stableRunRef.current = stableRun;
        applyRun(runningRun);
        onUpdate?.(runningRun);
        try {
          run = await pipelineApi.executeNode(run.id, nodeId, controller.signal);
        } catch (error) {
          if (!controller.signal.aborted) {
            applyRun(stableRun);
            onUpdate?.(stableRun);
          }
          throw error;
        } finally {
          if (executionController.current === controller) {
            stableRunRef.current = null;
          }
        }

        applyRun(run);
        onUpdate?.(run);
        const selectedState = run.nodes[nodeId];
        if (selectedState?.status === 'failed') {
          throw new Error(selectedState.error ?? '선택한 모듈 실행에 실패했습니다.');
        }
        return run;
      } finally {
        if (!controller.signal.aborted) setIsExecuting(false);
        if (executionController.current === controller) executionController.current = null;
      }
    },
    [applyRun, createRun, latestRun]
  );

  const cancelExecution = useCallback(() => {
    const epoch = ++runtimeMutationEpoch.current;
    const runId = latestRun?.id;
    executionController.current?.abort();
    executionController.current = null;
    if (stableRunRef.current) {
      applyRun(stableRunRef.current);
      stableRunRef.current = null;
    }
    setIsExecuting(false);
    if (runId) {
      void pipelineApi.cancelRun(runId).then((run) => {
        if (runtimeMutationEpoch.current === epoch) applyRun(run);
      }).catch(() => undefined);
    }
  }, [applyRun, latestRun]);

  const clearCache = useCallback(async () => {
    const epoch = ++runtimeMutationEpoch.current;
    const runId = latestRun?.id;
    executionController.current?.abort();
    executionController.current = null;
    stableRunRef.current = null;
    setIsExecuting(false);
    setIsClearingCache(true);
    try {
      if (runId) {
        try {
          await pipelineApi.cancelRun(runId);
        } catch (error) {
          if (!(error instanceof ApiError && error.status === 404)) throw error;
        }
      }
      const result = await pipelineApi.clearCache();
      if (runtimeMutationEpoch.current !== epoch) return result;
      setLatestRun(null);
      setRuns([]);
      graphRef.current.clearExecutionState();
      return result;
    } finally {
      setIsClearingCache(false);
    }
  }, [latestRun]);

  return {
    workflowId: ACTIVE_WORKFLOW_ID,
    ready,
    saveStatus,
    lastSavedAt,
    latestRun,
    runs,
    latestRunMatchesGraph,
    latestRunCompatibleWithGraph,
    isExecuting,
    isClearingCache,
    saveNow,
    executeAll,
    executeNext,
    executeNode,
    cancelExecution,
    clearCache,
  };
}
