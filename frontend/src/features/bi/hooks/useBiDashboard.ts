import { useEffect, useRef, useState } from 'react';
import {
  createBiMaterialization,
  fetchBiDashboard,
  refreshBiDashboard,
  resetBiDashboard,
  streamBiMaterializationJob,
  streamBiQuestionJob,
  BiApiRequestError,
} from '../services/api';
import type {
  BiCompanySummary,
  BiDashboardFetchResult,
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
  readonly activeAction: 'refresh' | 'reset' | null;
  readonly refresh: () => Promise<void>;
  readonly reset: () => Promise<void>;
  readonly retryMaterialization: () => Promise<void>;
}

const SNAPSHOT_PUBLICATION_POLL_INTERVAL_MS = 500;

function waitForSnapshotPublication(signal: AbortSignal): Promise<void> {
  if (signal.aborted) {
    return Promise.reject(signal.reason ?? new DOMException('Aborted', 'AbortError'));
  }
  return new Promise((resolve, reject) => {
    const onAbort = (): void => {
      window.clearTimeout(timer);
      reject(signal.reason ?? new DOMException('Aborted', 'AbortError'));
    };
    const timer = window.setTimeout(() => {
      signal.removeEventListener('abort', onAbort);
      resolve();
    }, SNAPSHOT_PUBLICATION_POLL_INTERVAL_MS);
    signal.addEventListener('abort', onAbort, { once: true });
  });
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
  throw new RangeError(`Unexpected BI state: ${String(value)}`);
}

export function useBiDashboard(
  company: BiCompanySummary | null,
): UseBiDashboardResult {
  const companyId = company?.companyId ?? '';
  const companyDisplayName = company?.displayName ?? '';
  const sourceFileName = company?.source?.fileName ?? '';
  const sourceWorkbookHash = company?.source?.workbookHash ?? '';
  const sourceIndexId = company?.source?.indexId ?? '';
  const [state, setState] = useState<BiDashboardState>({ status: 'idle' });
  const [activeAction, setActiveAction] = useState<'refresh' | 'reset' | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const dashboardRef = useRef<BiDashboardSnapshot | null>(null);

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
      refresh: { ...dashboard.refresh, status: 'failed', message },
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

  const publishResult = (
    result: BiDashboardFetchResult,
  ): string | null => {
    switch (result.kind) {
      case 'snapshot':
        dashboardRef.current = result.dashboard;
        setState({ status: 'ready', companyId, dashboard: result.dashboard });
        return result.dashboard.refresh.jobId
          && result.dashboard.refresh.status !== 'idle'
          && result.dashboard.refresh.status !== 'failed'
          ? result.dashboard.refresh.jobId
          : null;
      case 'pending':
        showJobProgress(result.job);
        return result.job.jobId;
      default:
        return assertNever(result);
    }
  };

  const loadPublishedSnapshot = async (
    controller: AbortController,
  ): Promise<string | null> => {
    const result = await fetchBiDashboard(companyId, controller.signal);
    if (!isCurrent(controller)) return null;
    return publishResult(result);
  };

  const loadReplacementSnapshot = async (
    previousSnapshotId: string,
    controller: AbortController,
  ): Promise<void> => {
    while (isCurrent(controller)) {
      const result = await fetchBiDashboard(companyId, controller.signal);
      if (!isCurrent(controller)) return;
      switch (result.kind) {
        case 'snapshot':
          if (
            result.dashboard.snapshot.snapshotId !== previousSnapshotId
            || result.dashboard.refresh.status === 'failed'
          ) {
            publishResult(result);
            return;
          }
          break;
        case 'pending':
          showJobProgress(result.job);
          if (result.job.status === 'failed') return;
          break;
        default:
          assertNever(result);
      }
      await waitForSnapshotPublication(controller.signal);
    }
  };

  const observeMaterialization = async (
    jobId: string,
    controller: AbortController,
  ): Promise<void> => {
    const job = await streamBiMaterializationJob(
      jobId,
      (progress) => {
        if (isCurrent(controller)) showJobProgress(progress);
      },
      controller.signal,
    );
    if (!isCurrent(controller)) return;
    if (job.status === 'failed') {
      showRefreshFailure(job.message ?? 'BI 스냅샷 생성에 실패했습니다.');
      return;
    }
    await loadPublishedSnapshot(controller);
  };

  useEffect(() => {
    if (!company) {
      dashboardRef.current = null;
      setState({ status: 'idle' });
      return undefined;
    }

    const controller = new AbortController();
    controllerRef.current = controller;
    dashboardRef.current = null;
    setActiveAction(null);
    setState({ status: 'loading', companyId });

    const load = async (): Promise<void> => {
      try {
        if (!company.currentSnapshotId) {
          if (company.refreshStatus === 'failed') {
            setState({
              status: 'error',
              companyId,
              message: '이 기업의 이전 BI 스냅샷 생성이 실패했습니다.',
            });
            return;
          }
          if (!company.source) {
            setState({
              status: 'error',
              companyId,
              message: 'BI 스냅샷을 만들 pgvector 원본이 없습니다.',
            });
            return;
          }
          const accepted = await createBiMaterialization({
            companyId: company.companyId,
            displayName: company.displayName,
            source: company.source,
          }, controller.signal);
          if (!isCurrent(controller)) return;
          await observeMaterialization(accepted.jobId, controller);
          return;
        }

        const activeJobId = await loadPublishedSnapshot(controller);
        if (activeJobId) await observeMaterialization(activeJobId, controller);
      } catch (error) {
        if (!isCurrent(controller)) return;
        showRefreshFailure(dashboardErrorMessage(error));
      }
    };

    void load();
    return () => controller.abort();
  }, [
    companyId,
    companyDisplayName,
    company?.currentSnapshotId,
    company?.refreshStatus,
    sourceFileName,
    sourceWorkbookHash,
    sourceIndexId,
  ]);

  const refresh = async (): Promise<void> => {
    const dashboard = dashboardRef.current;
    const controller = controllerRef.current;
    if (!dashboard || !controller || !isCurrent(controller)) return;
    setActiveAction('refresh');
    try {
      const refreshed = await refreshBiDashboard(companyId, controller.signal);
      if (!isCurrent(controller)) return;
      dashboardRef.current = refreshed;
      setState({ status: 'ready', companyId, dashboard: refreshed });
    } catch (error) {
      if (!isCurrent(controller)) return;
      showRefreshFailure(dashboardErrorMessage(error));
    } finally {
      if (isCurrent(controller)) setActiveAction(null);
    }
  };

  const reset = async (): Promise<void> => {
    const dashboard = dashboardRef.current;
    const controller = controllerRef.current;
    if (!dashboard || !controller || !isCurrent(controller)) return;
    const previousSnapshotId = dashboard.snapshot.snapshotId;
    setActiveAction('reset');
    try {
      const accepted = await resetBiDashboard(companyId, controller.signal);
      if (!isCurrent(controller)) return;
      showQuestionProgress(accepted);
      await streamBiQuestionJob(
        accepted.jobId,
        (progress) => {
          if (isCurrent(controller)) showQuestionProgress(progress);
        },
        controller.signal,
      );
      if (!isCurrent(controller)) return;
      await loadReplacementSnapshot(previousSnapshotId, controller);
    } catch (error) {
      if (!isCurrent(controller)) return;
      showRefreshFailure(dashboardErrorMessage(error));
    } finally {
      if (isCurrent(controller)) setActiveAction(null);
    }
  };

  const retryMaterialization = async (): Promise<void> => {
    const controller = controllerRef.current;
    if (!company?.source || !controller || !isCurrent(controller)) return;
    setState({ status: 'loading', companyId });
    try {
      const accepted = await createBiMaterialization({
        companyId: company.companyId,
        displayName: company.displayName,
        source: company.source,
      }, controller.signal);
      if (!isCurrent(controller)) return;
      await observeMaterialization(accepted.jobId, controller);
    } catch (error) {
      if (!isCurrent(controller)) return;
      showRefreshFailure(dashboardErrorMessage(error));
    }
  };

  return { state, activeAction, refresh, reset, retryMaterialization };
}
