import { useCallback, useEffect, useRef, useState } from 'react';
import { pipelineApi, ApiError } from '../services/api';
import type {
  SaveStatus,
  WorkflowGraph,
  WorkflowRun,
} from '../types';

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
    nodes: (graph.nodes ?? []).map(({ id, module_type, config, values }) => ({
      id,
      module_type,
      config: config ?? {},
      values: values ?? {},
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

function executionRunMatchesRequest(
  run: WorkflowRun,
  graph: WorkflowGraph,
  query: string,
): boolean {
  return executionFingerprint(run.graph) === executionFingerprint(graph)
    && JSON.stringify(run.runtime_inputs) === JSON.stringify(runInputs(graph, query));
}

const CANONICAL_WORKFLOW_IDS = new Set(['rag_query', 'excel_ingestion']);

async function pollRun(runId: string, signal: AbortSignal): Promise<WorkflowRun> {
  while (true) {
    const run = await pipelineApi.getRun(runId, signal);
    if (run.status === 'completed' || run.status === 'failed' || run.status === 'paused') {
      return run;
    }
    await new Promise<void>((resolve, reject) => {
      const onAbort = () => {
        window.clearTimeout(timeout);
        reject(new DOMException('Aborted', 'AbortError'));
      };
      const timeout = window.setTimeout(() => {
        signal.removeEventListener('abort', onAbort);
        resolve();
      }, 500);
      signal.addEventListener('abort', onAbort, { once: true });
    });
  }
}

/**
 * Manages workflow persistence, execution runs, cancellation, and cache clearing.
 *
 * @param graph - The workflow graph to load, update, and execute
 * @param moduleCatalogReady - Whether the module catalog is ready for workflow loading
 * @param activeWorkflowId - The identifier of the active workflow
 * @param activeWorkflowName - The name used when saving the active workflow
 * @returns Workflow state and controls for saving, executing, canceling, and clearing cached results
 */
export function useWorkflowPersistence(
  graph: WorkflowGraphBridge,
  moduleCatalogReady: boolean,
  activeWorkflowId: string,
  activeWorkflowName: string,
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
  const runtimeMutationEpoch = useRef(0);
  const latestRunMatchesGraph = Boolean(
    latestRun && executionFingerprint(latestRun.graph) === executionFingerprint(currentGraph)
  );
  const isCanonicalWorkflow = CANONICAL_WORKFLOW_IDS.has(activeWorkflowId);

  const applyRun = useCallback((run: WorkflowRun) => {
    setLatestRun(run);
    setRuns((currentRuns) =>
      [run, ...currentRuns.filter((candidate) => candidate.id !== run.id)]
        .sort((left, right) => right.updated_at.localeCompare(left.updated_at))
    );
    graphRef.current.applyRun(run);
  }, []);

  // Load workflow whenever activeWorkflowId changes
  useEffect(() => {
    if (!moduleCatalogReady) {
      setSaveStatus('loading');
      return;
    }
    const controller = new AbortController();

    // Cancel any running execution when switching workflows
    executionController.current?.abort();
    executionController.current = null;
    setIsExecuting(false);
    setReady(false);
    setLatestRun(null);
    setRuns([]);

    const load = async () => {
      setSaveStatus('loading');
      try {
        const workflow = await pipelineApi.getWorkflow(activeWorkflowId, controller.signal);
        graphRef.current.replaceGraph(workflow.graph);

        const response = await pipelineApi.getRuns(activeWorkflowId, controller.signal);
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
  }, [applyRun, moduleCatalogReady, activeWorkflowId, activeWorkflowName]);

  const saveNow = useCallback(async (signal?: AbortSignal) => {
    setSaveStatus('saving');
    try {
      const workflow = isCanonicalWorkflow
        ? await pipelineApi.getWorkflow(activeWorkflowId, signal)
        : await pipelineApi.saveWorkflow(
            activeWorkflowId,
            activeWorkflowName,
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
  }, [activeWorkflowId, activeWorkflowName, isCanonicalWorkflow]);

  useEffect(() => {
    if (!ready || isCanonicalWorkflow) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void saveNow(controller.signal).catch(() => undefined);
    }, 700);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [graphFingerprint, isCanonicalWorkflow, ready, saveNow]);

  const createRun = useCallback(
    async (query: string, signal: AbortSignal) => {
      const workflow = isCanonicalWorkflow
        ? await pipelineApi.getWorkflow(activeWorkflowId, signal)
        : await saveNow(signal);
      const run = await pipelineApi.createRun(
        activeWorkflowId,
        runInputs(workflow.graph, query),
        signal
      );
      applyRun(run);
      return run;
    },
    [activeWorkflowId, applyRun, isCanonicalWorkflow, saveNow]
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
        const currentRuntimeInputs = runInputs(currentExecutionGraph, query);
        let run = latestRun &&
          (latestRun.status === 'queued' ||
            latestRun.status === 'running' ||
            latestRun.status === 'paused' ||
            latestRun.status === 'failed') &&
          executionRunMatchesRequest(latestRun, currentExecutionGraph, query)
          && JSON.stringify(latestRun.runtime_inputs) === JSON.stringify(currentRuntimeInputs)
          ? latestRun
          : await createRun(query, controller.signal);
        if (run.status === 'failed' || run.status === 'paused') {
          run = await pipelineApi.resumeRun(run.id, controller.signal);
        }
        applyRun(run);
        onBatch?.(run);
        try {
          run = await pipelineApi.streamRun(
            run.id,
            (event) => {
              if (event.event === 'node_completed' || event.event === 'node_failed') {
                const nodeUpdate = event.data;
                if (nodeUpdate?.node_id) {
                  setLatestRun((prev) => {
                    if (!prev) return prev;
                    const existing = prev.nodes[nodeUpdate.node_id];
                    if (!existing) return prev;
                    const updated = {
                      ...prev,
                      nodes: {
                        ...prev.nodes,
                        [nodeUpdate.node_id]: { ...existing, ...nodeUpdate },
                      },
                    };
                    applyRun(updated);
                    onBatch?.(updated);
                    return updated;
                  });
                }
              } else if (event.event === 'run_completed' && event.data?.run) {
                applyRun(event.data.run);
                onBatch?.(event.data.run);
              }
            },
            controller.signal
          );
          applyRun(run);
          onBatch?.(run);
        } catch (streamError) {
          if (controller.signal.aborted) throw streamError;
          // The Kubernetes Job is durable. A dropped SSE connection only
          // changes observation transport; never execute modules in-browser/API.
          run = await pollRun(run.id, controller.signal);
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

  const cancelExecution = useCallback(() => {
    const epoch = ++runtimeMutationEpoch.current;
    const runId = latestRun?.id;
    executionController.current?.abort();
    executionController.current = null;
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
    workflowId: activeWorkflowId,
    workflowName: activeWorkflowName,
    ready,
    saveStatus,
    lastSavedAt,
    latestRun,
    runs,
    latestRunMatchesGraph,
    isCanonicalWorkflow,
    isExecuting,
    isClearingCache,
    saveNow,
    executeAll,
    cancelExecution,
    clearCache,
  };
}
