import type {
  ModuleDefinition,
  WorkflowDocument,
  WorkflowGraph,
  WorkflowRun,
} from '../types';
import {
  requestJson as httpJson,
} from '../../../shared/api/httpClient';
import {
  observeWorkflowRun,
  type WorkflowRunEvent,
} from '../../../shared/workflows/observeRun';

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

  getRunNode(runId: string, nodeId: string, signal?: AbortSignal) {
    return requestJson<WorkflowRun['nodes'][string]>(
      `/api/runs/${encodeURIComponent(runId)}/nodes/${encodeURIComponent(nodeId)}`,
      signal
    );
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
    onEvent: (event: WorkflowRunEvent) => void,
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

};
