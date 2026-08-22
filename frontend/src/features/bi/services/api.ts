import ky from 'ky';
import {
  parseBiCompanies,
  parseBiDashboard,
  parseBiMaterializationAccepted,
  parseBiMaterializationJob,
  parseBiPendingDashboard,
  parseBiQuestionJobProgress,
} from '../schemas';
import type {
  BiCompanyListResponse,
  BiDashboardFetchResult,
  BiMaterializationAccepted,
  BiMaterializationJob,
  BiMaterializationRequest,
  BiQuestionJobProgress,
} from '../types';

const REQUEST_OPTIONS = {
  retry: 0,
  timeout: 15_000,
  throwHttpErrors: false,
} as const;

export class BiApiRequestError extends Error {
  readonly name = 'BiApiRequestError';

  constructor(
    readonly status: number,
    readonly endpoint: string,
  ) {
    super(`BI API request failed with HTTP ${status}: ${endpoint}`);
  }
}

export async function fetchBiCompanies(signal: AbortSignal): Promise<BiCompanyListResponse> {
  const endpoint = '/api/bi/companies';
  const response = await ky.get(endpoint, { ...REQUEST_OPTIONS, signal });
  if (!response.ok) throw new BiApiRequestError(response.status, endpoint);
  return parseBiCompanies(await response.json<unknown>());
}

export async function fetchBiDashboard(
  companyId: string,
  signal: AbortSignal,
): Promise<BiDashboardFetchResult> {
  const endpoint = `/api/bi/companies/${encodeURIComponent(companyId)}/dashboard`;
  const response = await ky.get(endpoint, { ...REQUEST_OPTIONS, signal });
  const payload = await response.json<unknown>();
  if (response.status === 202) {
    return { kind: 'pending', job: parseBiPendingDashboard(payload) };
  }
  if (!response.ok) throw new BiApiRequestError(response.status, endpoint);
  return { kind: 'snapshot', dashboard: parseBiDashboard(payload) };
}

export async function createBiMaterialization(
  request: BiMaterializationRequest,
  signal: AbortSignal,
): Promise<BiMaterializationAccepted> {
  const endpoint = '/api/bi/materializations';
  const response = await ky.post(endpoint, {
    ...REQUEST_OPTIONS,
    signal,
    json: {
      company_id: request.companyId,
      display_name: request.displayName,
      source: {
        file_name: request.source.fileName,
        workbook_hash: request.source.workbookHash,
        index_id: request.source.indexId,
      },
    },
  });
  if (!response.ok) throw new BiApiRequestError(response.status, endpoint);
  return parseBiMaterializationAccepted(await response.json<unknown>());
}

export async function fetchBiMaterializationJob(
  jobId: string,
  signal: AbortSignal,
): Promise<BiMaterializationJob> {
  const endpoint = `/api/bi/materializations/${encodeURIComponent(jobId)}`;
  const response = await ky.get(endpoint, { ...REQUEST_OPTIONS, signal });
  if (!response.ok) throw new BiApiRequestError(response.status, endpoint);
  return parseBiMaterializationJob(await response.json<unknown>());
}

export async function refreshBiDashboard(
  companyId: string,
  signal: AbortSignal,
): Promise<BiQuestionJobProgress> {
  const endpoint = `/api/bi/companies/${encodeURIComponent(companyId)}/refresh`;
  const response = await ky.post(endpoint, { ...REQUEST_OPTIONS, signal });
  if (!response.ok) throw new BiApiRequestError(response.status, endpoint);
  return parseBiQuestionJobProgress(await response.json<unknown>());
}

export async function fetchBiQuestionJob(
  jobId: string,
  signal: AbortSignal,
): Promise<BiQuestionJobProgress> {
  const endpoint = `/api/bi/question-jobs/${encodeURIComponent(jobId)}`;
  const response = await ky.get(endpoint, { ...REQUEST_OPTIONS, signal });
  if (!response.ok) throw new BiApiRequestError(response.status, endpoint);
  return parseBiQuestionJobProgress(await response.json<unknown>());
}
