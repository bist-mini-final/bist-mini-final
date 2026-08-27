import { useCallback, useEffect, useRef, useState } from 'react';
import { BiApiRequestError, fetchBiCompanies } from '../services/api';
import type { BiCompanySummary } from '../types';

export type BiCompaniesState =
  | { readonly status: 'loading'; readonly companies: readonly [] }
  | { readonly status: 'ready'; readonly companies: readonly BiCompanySummary[] }
  | { readonly status: 'error'; readonly companies: readonly []; readonly message: string };

export interface BiCompaniesRefreshResult {
  readonly errorMessage: string | null;
}

interface BiCompaniesController {
  readonly state: BiCompaniesState;
  readonly refresh: () => Promise<BiCompaniesRefreshResult>;
}

function companyErrorMessage(error: unknown): string {
  if (error instanceof BiApiRequestError) {
    return `기업 목록을 불러오지 못했습니다. (HTTP ${error.status})`;
  }
  if (error instanceof Error) return '기업 목록 응답 형식을 확인할 수 없습니다.';
  return '기업 목록을 불러오지 못했습니다.';
}

export function useBiCompanies(): BiCompaniesController {
  const [state, setState] = useState<BiCompaniesState>({ status: 'loading', companies: [] });
  const activeControllerRef = useRef<AbortController | null>(null);

  const load = useCallback(async (
    preserveCurrentState: boolean,
  ): Promise<BiCompaniesRefreshResult> => {
    activeControllerRef.current?.abort();
    const controller = new AbortController();
    activeControllerRef.current = controller;

    try {
      const response = await fetchBiCompanies(controller.signal);
      if (!controller.signal.aborted) {
        setState({ status: 'ready', companies: response.companies });
      }
      return { errorMessage: null };
    } catch (error) {
      if (controller.signal.aborted) return { errorMessage: null };
      const message = companyErrorMessage(error);
      if (!preserveCurrentState) {
        setState({ status: 'error', companies: [], message: companyErrorMessage(error) });
      }
      return { errorMessage: message };
    }
  }, []);

  useEffect(() => {
    void load(false);
    return () => activeControllerRef.current?.abort();
  }, [load]);

  const refresh = useCallback(() => load(true), [load]);

  return {
    state,
    refresh,
  };
}
