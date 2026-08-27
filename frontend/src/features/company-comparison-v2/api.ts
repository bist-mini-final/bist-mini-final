import { requestJson } from '../../shared/api/httpClient';
import { parseCompanyComparisonV2 } from './schemas';
import type {
  CompanyComparisonV2Request,
  CompanyComparisonV2Response,
} from './types';

export async function analyzeCompanyComparisonV2(
  request: CompanyComparisonV2Request,
  signal: AbortSignal,
): Promise<CompanyComparisonV2Response> {
  const payload = await requestJson<unknown>('/api/v1/company-comparisons/analyze', {
    method: 'POST',
    signal,
    timeout: 120_000,
    json: {
      company_ids: request.companyIds,
      start_year: request.startYear,
      end_year: request.endYear,
      ...(request.question ? { question: request.question } : {}),
    },
  });
  return parseCompanyComparisonV2(payload);
}
