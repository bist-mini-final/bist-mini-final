import type {
  ModuleDefinition,
  ModuleType,
  BenchmarkCase,
  BenchmarkComparison,
  BenchmarkJob,
  WorkflowDocument,
  WorkflowGraph,
  WorkflowRun,
} from '../types';

interface ModuleResponse {
  modules: ModuleDefinition[];
}

export type SpreadsheetArtifactLayer = 'rendered' | 'typed' | 'docling';

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = 'ApiError';
  }
}

async function requestJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) {
    throw new ApiError(`요청을 처리하지 못했습니다. (${response.status})`, response.status);
  }
  return response.json() as Promise<T>;
}

async function writeJson<T>(
  method: 'POST' | 'PUT' | 'DELETE',
  url: string,
  payload?: unknown,
  signal?: AbortSignal
): Promise<T> {
  const response = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: payload === undefined ? undefined : JSON.stringify(payload),
    signal,
  });
  if (!response.ok) {
    let detail = `요청을 처리하지 못했습니다. (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === 'string') detail = body.detail;
    } catch {
      // Keep the status-based fallback when the response is not JSON.
    }
    throw new ApiError(detail, response.status);
  }
  return response.json() as Promise<T>;
}

function postJson<T>(url: string, payload?: unknown, signal?: AbortSignal): Promise<T> {
  return writeJson<T>('POST', url, payload, signal);
}

export const pipelineApi = {
  spreadsheetArtifactUrl(
    workbookHash: string,
    sheetName: string,
    layer: SpreadsheetArtifactLayer = 'rendered'
  ) {
    return `/api/spreadsheet-artifacts/${encodeURIComponent(workbookHash)}/sheets/${encodeURIComponent(sheetName)}?layer=${layer}`;
  },

  executeModule<T>(
    moduleType: ModuleType,
    input: unknown,
    config: Record<string, unknown> = {},
    signal?: AbortSignal
  ) {
    return postJson<T>(
      `/api/modules/${moduleType}/execute`,
      { input, config },
      signal
    );
  },

  getModules(signal?: AbortSignal) {
    return requestJson<ModuleResponse>('/api/modules', signal);
  },

  listWorkflows(signal?: AbortSignal) {
    return requestJson<{ workflows: WorkflowDocument[] }>('/api/workflows', signal);
  },

  getWorkflow(workflowId: string, signal?: AbortSignal) {
    return requestJson<WorkflowDocument>(`/api/workflows/${workflowId}`, signal);
  },

  saveWorkflow(
    workflowId: string,
    name: string,
    graph: WorkflowGraph,
    signal?: AbortSignal
  ) {
    return writeJson<WorkflowDocument>(
      'PUT',
      `/api/workflows/${workflowId}`,
      { name, graph },
      signal
    );
  },

  getRuns(workflowId: string, signal?: AbortSignal) {
    return requestJson<{ runs: WorkflowRun[] }>(
      `/api/runs?workflow_id=${encodeURIComponent(workflowId)}`,
      signal
    );
  },

  getRun(runId: string, signal?: AbortSignal) {
    return requestJson<WorkflowRun>(`/api/runs/${runId}`, signal);
  },

  createRun(
    workflowId: string,
    inputs: Record<string, Record<string, unknown>>,
    signal?: AbortSignal,
    inheritFromRunId?: string
  ) {
    return postJson<WorkflowRun>(
      `/api/workflows/${workflowId}/runs`,
      { inputs, use_cache: true, ...(inheritFromRunId ? { inherit_from_run_id: inheritFromRunId } : {}) },
      signal
    );
  },

  executeNextBatch(runId: string, signal?: AbortSignal) {
    return postJson<WorkflowRun>(`/api/runs/${runId}/execute-next`, undefined, signal);
  },

  executeNode(runId: string, nodeId: string, signal?: AbortSignal) {
    return postJson<WorkflowRun>(
      `/api/runs/${runId}/nodes/${encodeURIComponent(nodeId)}/execute`,
      undefined,
      signal
    );
  },

  cancelRun(runId: string, signal?: AbortSignal) {
    return postJson<WorkflowRun>(`/api/runs/${runId}/cancel`, undefined, signal);
  },

  resumeRun(runId: string, signal?: AbortSignal) {
    return postJson<WorkflowRun>(`/api/runs/${runId}/resume`, undefined, signal);
  },

  clearCache(signal?: AbortSignal) {
    return writeJson<{
      runs_removed: number;
      cache_entries_removed: number;
      answers_removed: number;
      embedding_artifacts_removed: number;
      vector_indexes_removed: number;
    }>(
      'DELETE',
      '/api/cache',
      undefined,
      signal
    );
  },

  deleteWorkflow(workflowId: string, signal?: AbortSignal) {
    return writeJson<{ deleted: string }>('DELETE', `/api/workflows/${workflowId}`, undefined, signal);
  },

  getWorkflows(signal?: AbortSignal) {
    return requestJson<{ workflows: WorkflowDocument[] }>('/api/workflows', signal);
  },

  compareBenchmarks(workflowIds: string[], cases: BenchmarkCase[], cacheMode: 'off' | 'all' | 'index_only' = 'index_only') {
    return postJson<BenchmarkComparison>('/api/benchmarks/compare', {
      workflow_ids: workflowIds,
      cases,
      use_cache: cacheMode === 'all', cache_mode: cacheMode,
    });
  },

  startBenchmarkJob(workflowIds: string[], cases: BenchmarkCase[], cacheMode: 'off' | 'all' | 'index_only' = 'index_only') {
    return postJson<{ id: string }>('/api/benchmarks/jobs', { workflow_ids: workflowIds, cases, use_cache: cacheMode === 'all', cache_mode: cacheMode });
  },

  getBenchmarkJob(jobId: string, signal?: AbortSignal) {
    return requestJson<BenchmarkJob>(`/api/benchmarks/jobs/${encodeURIComponent(jobId)}`, signal);
  },

  cancelBenchmarkJob(jobId: string) {
    return writeJson<{ id: string; status: string }>('DELETE', `/api/benchmarks/jobs/${encodeURIComponent(jobId)}`);
  },
};
