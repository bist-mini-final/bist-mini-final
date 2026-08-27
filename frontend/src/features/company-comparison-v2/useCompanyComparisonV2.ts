import { useCallback, useEffect, useRef, useState } from 'react';
import { analyzeCompanyComparisonV2 } from './api';
import type {
  CompanyComparisonV2Request,
  CompanyComparisonV2Response,
} from './types';

export type CompanyComparisonV2State =
  | { readonly status: 'idle' }
  | { readonly status: 'loading'; readonly previous: CompanyComparisonV2Response | null }
  | { readonly status: 'ready'; readonly result: CompanyComparisonV2Response }
  | { readonly status: 'error'; readonly message: string; readonly previous: CompanyComparisonV2Response | null };

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : 'RAG 기업 비교 분석에 실패했습니다.';
}

export function useCompanyComparisonV2() {
  const [state, setState] = useState<CompanyComparisonV2State>({ status: 'idle' });
  const controllerRef = useRef<AbortController | null>(null);
  const latestResultRef = useRef<CompanyComparisonV2Response | null>(null);

  useEffect(() => () => controllerRef.current?.abort(), []);

  const analyze = useCallback(async (request: CompanyComparisonV2Request) => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setState({ status: 'loading', previous: latestResultRef.current });
    try {
      const result = await analyzeCompanyComparisonV2(request, controller.signal);
      if (controller.signal.aborted) return;
      latestResultRef.current = result;
      setState({ status: 'ready', result });
    } catch (error) {
      if (controller.signal.aborted) return;
      setState({ status: 'error', message: messageOf(error), previous: latestResultRef.current });
    }
  }, []);

  return { state, analyze } as const;
}
