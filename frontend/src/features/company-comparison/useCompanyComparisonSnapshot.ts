import { useEffect, useState } from 'react';
import { fetchFinancialLeague } from './leagueApi';
import type { FinancialLeagueResponse } from './leagueTypes';

type State =
  | { readonly status: 'loading' }
  | { readonly status: 'error'; readonly message: string }
  | { readonly status: 'ready'; readonly data: FinancialLeagueResponse };

export function useFinancialLeague(reloadKey: number): State {
  const [state, setState] = useState<State>({ status: 'loading' });
  useEffect(() => {
    const controller = new AbortController();
    setState({ status: 'loading' });
    void fetchFinancialLeague(controller.signal).then(
      (data) => setState({ status: 'ready', data }),
      (error: unknown) => {
        if (!controller.signal.aborted) setState({ status: 'error', message: error instanceof Error ? error.message : '리그 데이터를 불러오지 못했습니다.' });
      },
    );
    return () => controller.abort();
  }, [reloadKey]);
  return state;
}
