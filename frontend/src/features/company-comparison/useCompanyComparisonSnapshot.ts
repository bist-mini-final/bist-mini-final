import { useEffect, useState } from 'react';
import {
  fetchCompanyComparisonSnapshot,
  refreshCompanyComparisonSnapshot,
} from './api';
import type { CompanyComparisonSnapshot } from './types';

type State =
  | { readonly status: 'loading' }
  | { readonly status: 'error'; readonly message: string }
  | { readonly status: 'ready'; readonly data: CompanyComparisonSnapshot };

export function useCompanyComparisonSnapshot(refreshKey: number): State {
  const [state, setState] = useState<State>({ status: 'loading' });
  useEffect(() => {
    const controller = new AbortController();
    setState({ status: 'loading' });
    const request = refreshKey === 0
      ? fetchCompanyComparisonSnapshot(controller.signal)
      : refreshCompanyComparisonSnapshot(controller.signal);
    void request.then(
      (data) => setState({ status: 'ready', data }),
      (error: unknown) => {
        if (!controller.signal.aborted) {
          setState({
            status: 'error',
            message: error instanceof Error
              ? error.message
              : '기업 비교 스냅샷을 불러오지 못했습니다.',
          });
        }
      },
    );
    return () => controller.abort();
  }, [refreshKey]);
  return state;
}
