import { useEffect, useRef, useState } from 'react';
import {
  BiApiRequestError,
  fetchBiDashboard,
  fetchBiMaterializationJob,
  fetchBiQuestionJob,
  refreshBiDashboard,
} from '../services/api';
import type {
  BiDashboardSnapshot,
  BiMaterializationJob,
  BiQuestionJobProgress,
  MaterializationStatus,
  RefreshStatus,
} from '../types';

export type BiDashboardState =
  | { readonly status: 'idle' }
  | { readonly status: 'loading'; readonly companyId: string }
  | { readonly status: 'ready'; readonly companyId: string; readonly dashboard: BiDashboardSnapshot }
  | { readonly status: 'pending'; readonly companyId: string; readonly job: BiMaterializationJob }
  | { readonly status: 'error'; readonly companyId: string; readonly message: string };

export interface UseBiDashboardResult {
  readonly state: BiDashboardState;
  readonly refresh: () => Promise<void>;
}

function dashboardErrorMessage(error: unknown): string {
  if (error instanceof BiApiRequestError) {
    return error.status === 404
      ? '이 기업에 게시된 BI 스냅샷이 없습니다.'
      : `대시보드를 불러오지 못했습니다. (HTTP ${error.status})`;
  }
  if (error instanceof Error) return '대시보드 응답 형식을 확인할 수 없습니다.';
  return '대시보드를 불러오지 못했습니다.';
}

function refreshStatus(status: MaterializationStatus): RefreshStatus {
  switch (status) {
    case 'queued':
    case 'indexing':
    case 'profiling':
    case 'extracting':
    case 'materializing':
    case 'failed':
      return status;
    case 'ready':
    case 'partial':
      return 'idle';
    default:
      return assertNever(status);
  }
}

function assertNever(value: never): never {
  throw new RangeError(`Unexpected materialization status: ${String(value)}`);
}

export function useBiDashboard(companyId: string): UseBiDashboardResult {
  const [state, setState] = useState<BiDashboardState>({ status: 'idle' });
  const controllerRef = useRef<AbortController | null>(null);
  const dashboardRef = useRef<BiDashboardSnapshot | null>(null);
  const pollTimerRef = useRef<number | null>(null);
  const pollAttemptRef = useRef(0);

  const isCurrent = (controller: AbortController): boolean => (
    controllerRef.current === controller && !controller.signal.aborted
  );

  const showRefreshFailure = (message: string): void => {
    const dashboard = dashboardRef.current;
    if (!dashboard) {
      setState({ status: 'error', companyId, message });
      return;
    }
    const failedDashboard = {
      ...dashboard,
      refresh: {
        ...dashboard.refresh,
        status: 'failed',
        message,
      },
    } satisfies BiDashboardSnapshot;
    dashboardRef.current = failedDashboard;
    setState({ status: 'ready', companyId, dashboard: failedDashboard });
  };

  const showJobProgress = (job: BiMaterializationJob): void => {
    const dashboard = dashboardRef.current;
    if (!dashboard) {
      setState({ status: 'pending', companyId, job });
      return;
    }
    const progressingDashboard = {
      ...dashboard,
      refresh: {
        status: refreshStatus(job.status),
        jobId: job.jobId,
        startedAt: job.startedAt,
        message: job.message,
      },
    } satisfies BiDashboardSnapshot;
    dashboardRef.current = progressingDashboard;
    setState({ status: 'ready', companyId, dashboard: progressingDashboard });
  };

  const showQuestionProgress = (progress: BiQuestionJobProgress): void => {
    const dashboard = dashboardRef.current;
    if (!dashboard) return;
    const finished = progress.completedQuestions + progress.failedQuestions;
    const failed = progress.failedQuestions > 0
      ? `, 실패 ${progress.failedQuestions}건은 NA 처리`
      : '';
    const progressingDashboard = {
      ...dashboard,
      refresh: {
        status: 'extracting',
        jobId: progress.jobId,
        startedAt: dashboard.refresh.startedAt,
        message: `지표 질문 ${finished}/${progress.totalQuestions}건 완료${failed}`,
      },
    } satisfies BiDashboardSnapshot;
    dashboardRef.current = progressingDashboard;
    setState({ status: 'ready', companyId, dashboard: progressingDashboard });
  };

  async function loadDashboard(controller: AbortController): Promise<void> {
    const result = await fetchBiDashboard(companyId, controller.signal);
    if (!isCurrent(controller)) return;
    switch (result.kind) {
      case 'snapshot':
        dashboardRef.current = result.dashboard;
        setState({ status: 'ready', companyId, dashboard: result.dashboard });
        if (result.dashboard.refresh.jobId && result.dashboard.refresh.status !== 'idle') {
          await pollQuestionJob(result.dashboard.refresh.jobId, controller);
        }
        return;
      case 'pending':
        setState({ status: 'pending', companyId, job: result.job });
        await pollJob(result.job.jobId, controller);
        return;
      default:
        return assertNever(result);
    }
  }

  async function pollJob(jobId: string, controller: AbortController): Promise<void> {
    try {
      const job = await fetchBiMaterializationJob(jobId, controller.signal);
      if (!isCurrent(controller)) return;
      switch (job.status) {
        case 'queued':
        case 'indexing':
        case 'profiling':
        case 'extracting':
        case 'materializing': {
          showJobProgress(job);
          const baseDelay = Math.min(1_000 * (2 ** pollAttemptRef.current), 8_000);
          pollAttemptRef.current += 1;
          const delay = document.visibilityState === 'hidden' ? Math.max(baseDelay, 5_000) : baseDelay;
          pollTimerRef.current = window.setTimeout(
            () => void pollJob(jobId, controller),
            delay,
          );
          return;
        }
        case 'ready':
        case 'partial': {
          pollAttemptRef.current = 0;
          const result = await fetchBiDashboard(companyId, controller.signal);
          if (!isCurrent(controller)) return;
          switch (result.kind) {
            case 'snapshot':
              dashboardRef.current = result.dashboard;
              setState({ status: 'ready', companyId, dashboard: result.dashboard });
              return;
            case 'pending':
              setState({ status: 'pending', companyId, job: result.job });
              return;
            default:
              return assertNever(result);
          }
        }
        case 'failed':
          showRefreshFailure(job.message ?? '새 데이터 처리에 실패해 이전 스냅샷을 유지합니다.');
          return;
        default:
          return assertNever(job.status);
      }
    } catch (error) {
      if (!isCurrent(controller)) return;
      showRefreshFailure(dashboardErrorMessage(error));
    }
  }

  async function pollQuestionJob(
    jobId: string,
    controller: AbortController,
  ): Promise<void> {
    try {
      const progress = await fetchBiQuestionJob(jobId, controller.signal);
      if (!isCurrent(controller)) return;
      if (progress.queuedQuestions > 0 || progress.runningQuestions > 0) {
        showQuestionProgress(progress);
        const baseDelay = Math.min(1_000 * (2 ** pollAttemptRef.current), 8_000);
        pollAttemptRef.current += 1;
        const delay = document.visibilityState === 'hidden'
          ? Math.max(baseDelay, 5_000)
          : baseDelay;
        pollTimerRef.current = window.setTimeout(
          () => void pollQuestionJob(jobId, controller),
          delay,
        );
        return;
      }
      pollAttemptRef.current = 0;
      const result = await fetchBiDashboard(companyId, controller.signal);
      if (!isCurrent(controller)) return;
      switch (result.kind) {
        case 'snapshot':
          dashboardRef.current = result.dashboard;
          setState({ status: 'ready', companyId, dashboard: result.dashboard });
          return;
        case 'pending':
          setState({ status: 'pending', companyId, job: result.job });
          return;
        default:
          return assertNever(result);
      }
    } catch (error) {
      if (!isCurrent(controller)) return;
      showRefreshFailure(dashboardErrorMessage(error));
    }
  }

  useEffect(() => {
    if (!companyId) {
      dashboardRef.current = null;
      setState({ status: 'idle' });
      return undefined;
    }

    const controller = new AbortController();
    controllerRef.current = controller;
    dashboardRef.current = null;
    pollAttemptRef.current = 0;
    setState({ status: 'loading', companyId });
    const load = async () => {
      try {
        await loadDashboard(controller);
      } catch (error) {
        if (!isCurrent(controller)) return;
        setState({ status: 'error', companyId, message: dashboardErrorMessage(error) });
      }
    };
    void load();
    return () => {
      controller.abort();
      if (pollTimerRef.current !== null) window.clearTimeout(pollTimerRef.current);
    };
  }, [companyId]);

  const refresh = async (): Promise<void> => {
    const dashboard = dashboardRef.current;
    const controller = controllerRef.current;
    if (!dashboard || !controller || !isCurrent(controller)) return;
    if (pollTimerRef.current !== null) window.clearTimeout(pollTimerRef.current);
    pollAttemptRef.current = 0;
    try {
      const accepted = await refreshBiDashboard(
        dashboard.company.companyId,
        controller.signal,
      );
      if (!isCurrent(controller)) return;
      const queuedDashboard = {
        ...dashboard,
        refresh: {
          status: 'queued',
          jobId: accepted.jobId,
          startedAt: new Date().toISOString(),
          message: `지표 질문 ${accepted.totalQuestions}건을 요청했습니다.`,
        },
      } satisfies BiDashboardSnapshot;
      dashboardRef.current = queuedDashboard;
      setState({ status: 'ready', companyId, dashboard: queuedDashboard });
      await pollQuestionJob(accepted.jobId, controller);
    } catch (error) {
      if (!isCurrent(controller)) return;
      showRefreshFailure(dashboardErrorMessage(error));
    }
  };

  return { state, refresh };
}
