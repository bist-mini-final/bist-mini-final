import type {
  ModuleDefinition,
  BenchmarkCase,
  BenchmarkSet,
  BenchmarkJob,
  WorkflowDocument,
  WorkflowGraph,
  WorkflowRun,
} from '../types';
import {
  requestJson as httpJson,
} from '../../../shared/api/httpClient';
import { observeWorkflowRun } from '../../../shared/workflows/observeRun';

export { ApiError } from '../../../shared/api/httpClient';

interface ModuleResponse {
  modules: ModuleDefinition[];
}

export type SpreadsheetArtifactLayer = 'rendered' | 'typed';

async function requestJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  return httpJson<T>(url, { signal });
}

async function writeJson<T>(
  method: 'POST' | 'PUT' | 'DELETE',
  url: string,
  payload?: unknown,
  signal?: AbortSignal
): Promise<T> {
  return httpJson<T>(url, {
    method,
    json: payload,
    signal,
  });
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
    signal?: AbortSignal
  ) {
    return postJson<WorkflowRun>(
      `/api/workflows/${workflowId}/runs`,
      { inputs, use_cache: true },
      signal
    );
  },

  cancelRun(runId: string, signal?: AbortSignal) {
    return postJson<WorkflowRun>(`/api/runs/${runId}/cancel`, undefined, signal);
  },

  resumeRun(runId: string, signal?: AbortSignal) {
    return postJson<WorkflowRun>(`/api/runs/${runId}/resume`, undefined, signal);
  },

  async streamRun(
    runId: string,
    onEvent: (event: { event: string; data: any }) => void,
    signal?: AbortSignal
  ): Promise<WorkflowRun> {
    return observeWorkflowRun(runId, { onEvent, signal });
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

  getBenchmarkSets(signal?: AbortSignal) {
    return requestJson<{ benchmark_sets: BenchmarkSet[] }>('/api/benchmark-sets', signal);
  },

  startBenchmarkJob(workflowIds: string[], cases: BenchmarkCase[], cacheMode: 'off' | 'all' | 'index_only' = 'index_only', executionScope: 'full' | 'pre_retrieval' = 'full') {
    return postJson<{ id: string }>('/api/benchmarks/jobs', { workflow_ids: workflowIds, cases, use_cache: cacheMode === 'all', cache_mode: cacheMode, execution_scope: executionScope });
  },

  getBenchmarkJob(jobId: string, signal?: AbortSignal) {
    return requestJson<BenchmarkJob>(`/api/benchmarks/jobs/${encodeURIComponent(jobId)}`, signal);
  },

  cancelBenchmarkJob(jobId: string) {
    return writeJson<{ id: string; status: string }>('DELETE', `/api/benchmarks/jobs/${encodeURIComponent(jobId)}`);
  },

  pauseBenchmarkJob(jobId: string) {
    return postJson<{ id: string; status: string }>(`/api/benchmarks/jobs/${encodeURIComponent(jobId)}/pause`);
  },

  resumeBenchmarkJob(jobId: string) {
    return postJson<{ id: string; status: string }>(`/api/benchmarks/jobs/${encodeURIComponent(jobId)}/resume`);
  },
};
