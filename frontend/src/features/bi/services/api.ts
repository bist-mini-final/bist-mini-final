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
import {
  requestJson,
  requestResponse,
} from '../../../shared/api/httpClient';

export { ApiError as BiApiRequestError } from '../../../shared/api/httpClient';

export async function fetchBiCompanies(signal: AbortSignal): Promise<BiCompanyListResponse> {
  const endpoint = '/api/bi/companies';
  return parseBiCompanies(await requestJson<unknown>(endpoint, { signal }));
}

export async function fetchBiDashboard(
  companyId: string,
  signal: AbortSignal,
): Promise<BiDashboardFetchResult> {
  const endpoint = `/api/bi/companies/${encodeURIComponent(companyId)}/dashboard`;
  const response = await requestResponse(endpoint, { signal });
  const payload = await response.json() as unknown;
  if (response.status === 202) {
    return { kind: 'pending', job: parseBiPendingDashboard(payload) };
  }
  return { kind: 'snapshot', dashboard: parseBiDashboard(payload) };
}

export async function createBiMaterialization(
  request: BiMaterializationRequest,
  signal: AbortSignal,
): Promise<BiMaterializationAccepted> {
  const endpoint = '/api/bi/materializations';
  const payload = await requestJson<unknown>(endpoint, {
    method: 'POST',
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
  return parseBiMaterializationAccepted(payload);
}

export async function fetchBiMaterializationJob(
  jobId: string,
  signal: AbortSignal,
): Promise<BiMaterializationJob> {
  const endpoint = `/api/bi/materializations/${encodeURIComponent(jobId)}`;
  return parseBiMaterializationJob(
    await requestJson<unknown>(endpoint, { signal }),
  );
}

export async function refreshBiDashboard(
  companyId: string,
  signal: AbortSignal,
): Promise<BiQuestionJobProgress> {
  const endpoint = `/api/bi/companies/${encodeURIComponent(companyId)}/refresh`;
  return parseBiQuestionJobProgress(
    await requestJson<unknown>(endpoint, { method: 'POST', signal }),
  );
}

export async function fetchBiQuestionJob(
  jobId: string,
  signal: AbortSignal,
): Promise<BiQuestionJobProgress> {
  const endpoint = `/api/bi/question-jobs/${encodeURIComponent(jobId)}`;
  return parseBiQuestionJobProgress(
    await requestJson<unknown>(endpoint, { signal }),
  );
}
