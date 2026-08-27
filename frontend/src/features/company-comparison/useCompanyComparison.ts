import { useEffect, useState } from 'react';
import { fetchBiCompanies, fetchBiDashboard } from '../bi/services/api';
import {
  COMPARISON_COMPANIES,
  type ComparisonDashboard,
} from './comparison';

type ComparisonLoadState =
  | { readonly status: 'loading' }
  | { readonly status: 'error'; readonly message: string }
  | { readonly status: 'ready'; readonly companies: readonly ComparisonDashboard[] };

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '기업 비교 데이터를 불러오지 못했습니다.';
}

export function useCompanyComparison(reloadKey: number): ComparisonLoadState {
  const [state, setState] = useState<ComparisonLoadState>({ status: 'loading' });

  useEffect(() => {
    const controller = new AbortController();
    setState({ status: 'loading' });
    void (async () => {
      try {
        const response = await fetchBiCompanies(controller.signal);
        const selected = COMPARISON_COMPANIES.map((target) => {
          const candidates = response.companies.filter((company) => (
            target.matches.test(company.displayName)
            && company.source !== null
            && company.snapshotStatus !== null
            && company.currentSnapshotId !== null
          ));
          const company = candidates.find((candidate) => (
            candidate.snapshotStatus === 'ready'
            && candidate.source?.fileName.includes('_AI_DX_')
          )) ?? candidates.find((candidate) => candidate.snapshotStatus === 'ready') ?? candidates[0];
          if (!company) throw new Error(`${target.label}의 검증된 BI 스냅샷을 찾지 못했습니다.`);
          return { target, company };
        });
        const dashboards = await Promise.all(selected.map(async ({ target, company }) => {
          const result = await fetchBiDashboard(company.companyId, controller.signal);
          if (result.kind === 'pending') {
            throw new Error(`${target.label} 데이터가 아직 생성 중입니다. 잠시 후 다시 시도해 주세요.`);
          }
          return {
            key: target.key,
            label: target.label,
            color: target.color,
            dashboard: result.dashboard,
          } satisfies ComparisonDashboard;
        }));
        setState({ status: 'ready', companies: dashboards });
      } catch (error) {
        if (controller.signal.aborted) return;
        setState({ status: 'error', message: errorMessage(error) });
      }
    })();
    return () => controller.abort();
  }, [reloadKey]);

  return state;
}
