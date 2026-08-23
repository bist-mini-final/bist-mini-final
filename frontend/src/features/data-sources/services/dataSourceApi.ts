import type {
  DbStatusInfo,
  DeleteIngestionJobResponse,
  IngestionJobResponse,
  SearchResponse,
  VectorIndexDetail,
  VectorIndexInfo,
} from '../types';
import {
  requestJson as httpJson,
  requestResponse,
} from '../../../shared/api/httpClient';
import { observeWorkflowRun } from '../../../shared/workflows/observeRun';

async function requestJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  return httpJson<T>(url, { signal });
}

async function postJson<T>(url: string, payload: unknown, signal?: AbortSignal): Promise<T> {
  return httpJson<T>(url, {
    method: 'POST',
    json: payload,
    signal,
  });
}

async function patchJson<T>(url: string, payload: unknown, signal?: AbortSignal): Promise<T> {
  return httpJson<T>(url, {
    method: 'PATCH',
    json: payload,
    signal,
  });
}

/**
 * Sends a DELETE request and parses the successful JSON response.
 *
 * @param url - The request URL
 * @returns The parsed response data
 */
async function deleteJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  return httpJson<T>(url, {
    method: 'DELETE',
    signal,
  }, '삭제 실패');
}

export const dataSourceApi = {
  async uploadFile(
    file: File,
    autoIngest: boolean = true,
    model: string = 'text-embedding-3-small',
    batchSize: number = 2048,
    signal?: AbortSignal
  ): Promise<{
    ingestion_job?: IngestionJobResponse;
    error?: string;
  }> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await requestResponse(
      `/api/data-sources/files/upload?auto_ingest=${autoIngest}&model=${encodeURIComponent(model)}&batch_size=${batchSize}`,
      {
        method: 'POST',
        body: formData,
        signal,
      },
      '업로드 실패',
    );
    return response.json();
  },

  async listIndexes(signal?: AbortSignal): Promise<VectorIndexInfo[]> {
    const data = await requestJson<{ indexes: VectorIndexInfo[]; total: number }>(
      '/api/data-sources/indexes',
      signal
    );
    return data.indexes;
  },

  async getIndexDetail(indexId: string, signal?: AbortSignal): Promise<VectorIndexDetail> {
    return requestJson<VectorIndexDetail>(
      `/api/data-sources/indexes/${encodeURIComponent(indexId)}`,
      signal
    );
  },

  async deleteIndex(indexId: string, signal?: AbortSignal): Promise<void> {
    await deleteJson(`/api/data-sources/indexes/${encodeURIComponent(indexId)}`, signal);
  },

  async updateIndexCompany(
    indexId: string,
    companyName: string,
    signal?: AbortSignal
  ): Promise<VectorIndexDetail> {
    return patchJson<VectorIndexDetail>(
      `/api/data-sources/indexes/${encodeURIComponent(indexId)}`,
      { company_name: companyName },
      signal
    );
  },

  async searchIndex(
    indexId: string,
    query: string,
    limit = 5,
    signal?: AbortSignal
  ): Promise<SearchResponse> {
    return postJson<SearchResponse>(
      `/api/data-sources/indexes/${encodeURIComponent(indexId)}/search`,
      { query, limit },
      signal
    );
  },

  async getDbStatus(signal?: AbortSignal): Promise<DbStatusInfo> {
    return requestJson<DbStatusInfo>('/api/data-sources/db-status', signal);
  },

  async listIngestionJobs(
    fileName?: string,
    signal?: AbortSignal
  ): Promise<IngestionJobResponse[]> {
    const query = fileName ? `?file_name=${encodeURIComponent(fileName)}` : '';
    const data = await requestJson<{ jobs: IngestionJobResponse[]; total: number }>(
      `/api/data-sources/ingestion-jobs${query}`,
      signal
    );
    return data.jobs;
  },

  async getIngestionJob(
    runId: string,
    signal?: AbortSignal
  ): Promise<IngestionJobResponse> {
    return requestJson<IngestionJobResponse>(
      `/api/data-sources/ingestion-jobs/${encodeURIComponent(runId)}`,
      signal
    );
  },

  async streamIngestionJob(
    initialJob: IngestionJobResponse,
    onUpdate: (job: IngestionJobResponse) => void,
    signal?: AbortSignal,
  ): Promise<IngestionJobResponse> {
    let projected = initialJob;
    const run = await observeWorkflowRun(initialJob.job_id, {
      initialRun: initialJob.run,
      signal,
      onRun(nextRun) {
        projected = {
          ...projected,
          status: nextRun.status,
          run: nextRun,
          worker_active: nextRun.status === 'running',
        };
        onUpdate(projected);
      },
    });
    projected = { ...projected, status: run.status, run, worker_active: false };
    try {
      projected = await this.getIngestionJob(initialJob.job_id, signal);
    } catch (error) {
      if (signal?.aborted) throw error;
    }
    onUpdate(projected);
    return projected;
  },

  async getIngestionJobByIndex(
    indexId: string,
    signal?: AbortSignal
  ): Promise<IngestionJobResponse> {
    return requestJson<IngestionJobResponse>(
      `/api/data-sources/ingestion-jobs/by-index/${encodeURIComponent(indexId)}`,
      signal
    );
  },

  async resumeIngestionJob(
    runId: string,
    signal?: AbortSignal
  ): Promise<IngestionJobResponse> {
    return postJson<IngestionJobResponse>(
      `/api/data-sources/ingestion-jobs/${encodeURIComponent(runId)}/resume`,
      {},
      signal
    );
  },

  async cancelIngestionJob(
    runId: string,
    signal?: AbortSignal
  ): Promise<IngestionJobResponse> {
    return postJson<IngestionJobResponse>(
      `/api/data-sources/ingestion-jobs/${encodeURIComponent(runId)}/cancel`,
      {},
      signal
    );
  },

  async deleteIngestionJob(
    runId: string,
    signal?: AbortSignal
  ): Promise<DeleteIngestionJobResponse> {
    return deleteJson<DeleteIngestionJobResponse>(
      `/api/data-sources/ingestion-jobs/${encodeURIComponent(runId)}`,
      signal
    );
  },
};
