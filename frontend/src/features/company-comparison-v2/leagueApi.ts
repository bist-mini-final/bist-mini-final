import { requestJson } from '../../shared/api/httpClient';
import { parseFinancialLeague } from './leagueSchema';

export async function fetchFinancialLeague(signal: AbortSignal) {
  return parseFinancialLeague(await requestJson<unknown>('/api/v1/company-comparisons/league', { signal }));
}
