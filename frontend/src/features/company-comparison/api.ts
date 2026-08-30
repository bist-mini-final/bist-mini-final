import { requestJson } from '../../shared/api/httpClient';
import { parseCompanyComparisonSnapshot } from './schemas';

export async function fetchCompanyComparisonSnapshot(signal: AbortSignal) {
  const payload = await requestJson<unknown>('/api/v1/company-comparisons/snapshot', { signal });
  return parseCompanyComparisonSnapshot(payload);
}

export async function refreshCompanyComparisonSnapshot(signal: AbortSignal) {
  const payload = await requestJson<unknown>('/api/v1/company-comparisons/snapshot/refresh', {
    method: 'POST',
    signal,
    timeout: 60_000,
  });
  return parseCompanyComparisonSnapshot(payload);
}
