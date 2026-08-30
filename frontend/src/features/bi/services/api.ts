import {
  parseBiCompanies,
  parseBiDashboard,
  parseBiMaterializationAccepted,
  parseBiMaterializationCandidates,
  parseBiMaterializationJob,
  parseBiPendingDashboard,
  parseBiQuestionJobProgress,
} from '../schemas';
import type {
  BiCompanyListResponse,
  BiDashboardSnapshot,
  BiDashboardFetchResult,
  BiMaterializationAccepted,
  BiMaterializationCandidateListResponse,
  BiMaterializationJob,
  BiMaterializationRequest,
  BiQuestionJobProgress,
} from '../types';
import {
  requestJson,
  requestResponse,
} from '../../../shared/api/httpClient';
import { streamJsonEvents } from '../../../shared/api/sse';

export { ApiError as BiApiRequestError } from '../../../shared/api/httpClient';

const BI_API_PREFIX = '/api/v1/bi';

export async function fetchBiCompanies(signal: AbortSignal): Promise<BiCompanyListResponse> {
  const endpoint = `${BI_API_PREFIX}/companies`;
  return parseBiCompanies(await requestJson<unknown>(endpoint, { signal }));
}

export async function fetchBiMaterializationCandidates(
  signal: AbortSignal,
): Promise<BiMaterializationCandidateListResponse> {
  const endpoint = `${BI_API_PREFIX}/materialization-candidates`;
  return parseBiMaterializationCandidates(
    await requestJson<unknown>(endpoint, { signal }),
  );
}

export async function fetchBiDashboard(
  companyId: string,
  signal: AbortSignal,
): Promise<BiDashboardFetchResult> {
  const endpoint = `${BI_API_PREFIX}/companies/${encodeURIComponent(companyId)}/dashboard`;
  const response = await requestResponse(endpoint, { signal });
  const payload = await response.json() as unknown;
  if (response.status === 202) {
    return { kind: 'pending', job: parseBiPendingDashboard(payload) };
  }
  return { kind: 'snapshot', dashboard: parseBiDashboard(payload) };
}

export async function deleteBiDashboard(
  companyId: string,
  signal: AbortSignal,
): Promise<void> {
  const endpoint = `${BI_API_PREFIX}/companies/${encodeURIComponent(companyId)}/dashboard`;
  await requestResponse(endpoint, { method: 'DELETE', signal });
}

export async function createBiMaterialization(
  request: BiMaterializationRequest,
  signal: AbortSignal,
): Promise<BiMaterializationAccepted> {
  const endpoint = `${BI_API_PREFIX}/materializations`;
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
  const endpoint = `${BI_API_PREFIX}/materializations/${encodeURIComponent(jobId)}`;
  return parseBiMaterializationJob(
    await requestJson<unknown>(endpoint, { signal }),
  );
}

function waitForReconnect(signal: AbortSignal): Promise<void> {
  if (signal.aborted) return Promise.reject(signal.reason);
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(resolve, 500);
    signal.addEventListener('abort', () => {
      window.clearTimeout(timer);
      reject(signal.reason);
    }, { once: true });
  });
}

export async function streamBiMaterializationJob(
  jobId: string,
  onUpdate: (job: BiMaterializationJob) => void,
  signal: AbortSignal,
): Promise<BiMaterializationJob> {
  let latest: BiMaterializationJob | null = null;
  const endpoint = `${BI_API_PREFIX}/materializations/${encodeURIComponent(jobId)}/stream`;
  while (!signal.aborted) {
    try {
      await streamJsonEvents(endpoint, (event) => {
        if (!event.event.startsWith('materialization_')) return;
        latest = parseBiMaterializationJob(event.data);
        onUpdate(latest);
      }, signal);
    } catch (error) {
      if (signal.aborted) throw error;
    }
    if (latest && ['ready', 'partial', 'failed'].includes(latest.status)) return latest;
    latest = await fetchBiMaterializationJob(jobId, signal);
    onUpdate(latest);
    if (['ready', 'partial', 'failed'].includes(latest.status)) return latest;
    await waitForReconnect(signal);
  }
  throw signal.reason ?? new DOMException('Aborted', 'AbortError');
}

export async function refreshBiDashboard(
  companyId: string,
  signal: AbortSignal,
): Promise<BiDashboardSnapshot> {
  const endpoint = `${BI_API_PREFIX}/companies/${encodeURIComponent(companyId)}/refresh`;
  return parseBiDashboard(
    await requestJson<unknown>(endpoint, { method: 'POST', signal }),
  );
}

export async function resetBiDashboard(
  companyId: string,
  signal: AbortSignal,
): Promise<BiQuestionJobProgress> {
  const endpoint = `${BI_API_PREFIX}/companies/${encodeURIComponent(companyId)}/reset`;
  return parseBiQuestionJobProgress(
    await requestJson<unknown>(endpoint, { method: 'POST', signal }),
  );
}

export async function fetchBiQuestionJob(
  jobId: string,
  signal: AbortSignal,
): Promise<BiQuestionJobProgress> {
  const endpoint = `${BI_API_PREFIX}/question-jobs/${encodeURIComponent(jobId)}`;
  return parseBiQuestionJobProgress(
    await requestJson<unknown>(endpoint, { signal }),
  );
}

export async function streamBiQuestionJob(
  jobId: string,
  onUpdate: (progress: BiQuestionJobProgress) => void,
  signal: AbortSignal,
): Promise<BiQuestionJobProgress> {
  let latest: BiQuestionJobProgress | null = null;
  const endpoint = `${BI_API_PREFIX}/question-jobs/${encodeURIComponent(jobId)}/stream`;
  while (!signal.aborted) {
    try {
      await streamJsonEvents(endpoint, (event) => {
        if (!event.event.startsWith('question_job_')) return;
        latest = parseBiQuestionJobProgress(event.data);
        onUpdate(latest);
      }, signal);
    } catch (error) {
      if (signal.aborted) throw error;
    }
    if (latest && latest.queuedQuestions === 0 && latest.runningQuestions === 0) {
      return latest;
    }
    latest = await fetchBiQuestionJob(jobId, signal);
    onUpdate(latest);
    if (latest.queuedQuestions === 0 && latest.runningQuestions === 0) return latest;
    await waitForReconnect(signal);
  }
  throw signal.reason ?? new DOMException('Aborted', 'AbortError');
}
