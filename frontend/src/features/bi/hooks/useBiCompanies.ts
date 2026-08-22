import { useEffect, useState } from 'react';
import { BiApiRequestError, fetchBiCompanies } from '../services/api';
import type { BiCompanySummary } from '../types';

export type BiCompaniesState =
  | { readonly status: 'loading'; readonly companies: readonly [] }
  | { readonly status: 'ready'; readonly companies: readonly BiCompanySummary[] }
  | { readonly status: 'error'; readonly companies: readonly []; readonly message: string };

function companyErrorMessage(error: unknown): string {
  if (error instanceof BiApiRequestError) {
    return `기업 목록을 불러오지 못했습니다. (HTTP ${error.status})`;
  }
  if (error instanceof Error) return '기업 목록 응답 형식을 확인할 수 없습니다.';
  return '기업 목록을 불러오지 못했습니다.';
}

export function useBiCompanies(): BiCompaniesState {
  const [state, setState] = useState<BiCompaniesState>({ status: 'loading', companies: [] });

  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      try {
        const response = await fetchBiCompanies(controller.signal);
        if (!controller.signal.aborted) {
          setState({ status: 'ready', companies: response.companies });
        }
      } catch (error) {
        if (controller.signal.aborted) return;
        setState({ status: 'error', companies: [], message: companyErrorMessage(error) });
      }
    };
    void load();
    return () => controller.abort();
  }, []);

  return state;
}
