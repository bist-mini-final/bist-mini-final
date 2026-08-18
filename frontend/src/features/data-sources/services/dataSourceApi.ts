import type {
  DataSourceFile,
  DbStatusInfo,
  IngestRequest,
  SearchResponse,
  SheetPreviewData,
  VectorIndexDetail,
  VectorIndexInfo,
} from '../types';

export class DataSourceApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = 'DataSourceApiError';
  }
}

async function requestJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) {
    let detail = `요청 실패 (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (typeof body.detail === 'string') detail = body.detail;
    } catch {
      // fallback
    }
    throw new DataSourceApiError(detail, response.status);
  }
  return response.json() as Promise<T>;
}

async function postJson<T>(url: string, payload: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  });
  if (!response.ok) {
    let detail = `요청 실패 (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (typeof body.detail === 'string') detail = body.detail;
    } catch {
      // fallback
    }
    throw new DataSourceApiError(detail, response.status);
  }
  return response.json() as Promise<T>;
}

async function patchJson<T>(url: string, payload: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  });
  if (!response.ok) {
    let detail = `요청 실패 (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (typeof body.detail === 'string') detail = body.detail;
    } catch {
      // fallback
    }
    throw new DataSourceApiError(detail, response.status);
  }
  return response.json() as Promise<T>;
}

async function deleteJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, {
    method: 'DELETE',
    signal,
  });
  if (!response.ok) {
    let detail = `삭제 실패 (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (typeof body.detail === 'string') detail = body.detail;
    } catch {
      // fallback
    }
    throw new DataSourceApiError(detail, response.status);
  }
  return response.json() as Promise<T>;
}

export const dataSourceApi = {
  async listFiles(signal?: AbortSignal): Promise<DataSourceFile[]> {
    const data = await requestJson<{ files: DataSourceFile[]; total: number }>(
      '/api/data-sources/files',
      signal
    );
    return data.files;
  },

  async previewSheet(
    fileName: string,
    sheetName?: string,
    maxRows = 15,
    signal?: AbortSignal
  ): Promise<SheetPreviewData> {
    const url = `/api/data-sources/files/${encodeURIComponent(fileName)}/preview?max_rows=${maxRows}${
      sheetName ? `&sheet_name=${encodeURIComponent(sheetName)}` : ''
    }`;
    return requestJson<SheetPreviewData>(url, signal);
  },

  async uploadFile(
    file: File,
    autoIngest: boolean = true,
    model: string = 'text-embedding-3-large',
    batchSize: number = 64,
    signal?: AbortSignal
  ): Promise<{ file: DataSourceFile; auto_ingested: boolean; ingested_index?: any; error?: string }> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(
      `/api/data-sources/files/upload?auto_ingest=${autoIngest}&model=${encodeURIComponent(model)}&batch_size=${batchSize}`,
      {
        method: 'POST',
        body: formData,
        signal,
      }
    );

    if (!response.ok) {
      let detail = `업로드 실패 (${response.status})`;
      try {
        const body = (await response.json()) as { detail?: string };
        if (typeof body.detail === 'string') detail = body.detail;
      } catch {
        // fallback
      }
      throw new DataSourceApiError(detail, response.status);
    }

    return response.json();
  },

  async deleteFile(fileName: string, signal?: AbortSignal): Promise<void> {
    await deleteJson(`/api/data-sources/files/${encodeURIComponent(fileName)}`, signal);
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

  async testDbConnect(databaseUrl: string, signal?: AbortSignal): Promise<DbStatusInfo> {
    return postJson<DbStatusInfo>('/api/data-sources/db-connect', { database_url: databaseUrl }, signal);
  },

  async ingestWorkbook(
    payload: IngestRequest,
    signal?: AbortSignal
  ): Promise<VectorIndexInfo> {
    const data = await postJson<{ status: string; index: VectorIndexInfo }>(
      '/api/data-sources/ingest',
      payload,
      signal
    );
    return data.index;
  },
};
