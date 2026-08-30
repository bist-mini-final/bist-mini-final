import { useCallback, useEffect, useMemo, useState } from 'react';
import type { PipelineRunState } from './pipelineTypes';
import { dataSourceApi } from './services/dataSourceApi';
import type { DbStatusInfo, IngestionJobResponse, VectorIndexInfo } from './types';
import { pipelineFromIngestionJob } from './workflowIngestion';

const ACTIVE_JOB_KEY = 'ds_active_ingestion_job_id';
const PENDING_FILE_KEY = 'ds_pending_ingestion_file_name';
const RESTORABLE_JOB_STATUSES = new Set<IngestionJobResponse['status']>([
  'queued',
  'running',
  'paused',
]);

export type DeleteTarget =
  | { readonly type: 'index'; readonly indexId: string }
  | { readonly type: 'pipeline'; readonly run: PipelineRunState };

export function findRestorableIngestionJob(
  jobs: IngestionJobResponse[],
): IngestionJobResponse | null {
  return jobs.find((job) => RESTORABLE_JOB_STATUSES.has(job.status)) ?? null;
}

function isServerRun(pipelineId?: string): boolean {
  return Boolean(pipelineId?.startsWith('run-'));
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === 'AbortError';
}

function latestFailedRuns(jobs: IngestionJobResponse[]): PipelineRunState[] {
  const seenFiles = new Set<string>();
  const failures: PipelineRunState[] = [];
  for (const job of jobs) {
    const pipeline = pipelineFromIngestionJob(job);
    if (seenFiles.has(pipeline.fileName)) continue;
    seenFiles.add(pipeline.fileName);
    if (pipeline.status === 'failed') failures.push(pipeline);
  }
  return failures;
}

/** Owns server synchronization and transient actions for the data sources workspace. */
export function useDataSourcesController() {
  const [indexes, setIndexes] = useState<VectorIndexInfo[]>([]);
  const [dbStatus, setDbStatus] = useState<DbStatusInfo | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activePipelineRun, setActivePipelineRun] = useState<PipelineRunState | null>(null);
  const [isViewingTracker, setIsViewingTracker] = useState(false);
  const [isCancellingPipeline, setIsCancellingPipeline] = useState(false);
  const [deletingPipelineId, setDeletingPipelineId] = useState<string | null>(null);
  const [deletingIndexId, setDeletingIndexId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [failedRuns, setFailedRuns] = useState<PipelineRunState[]>([]);
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [detailIndexId, setDetailIndexId] = useState<string | null>(null);
  const [searchTargetIndex, setSearchTargetIndex] = useState<VectorIndexInfo | null>(null);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [indexesResponse, dbResponse, jobsResponse] = await Promise.all([
        dataSourceApi.listIndexes(),
        dataSourceApi.getDbStatus().catch(() => null),
        dataSourceApi.listIngestionJobs().catch(() => []),
      ]);
      setIndexes(indexesResponse);
      if (dbResponse) setDbStatus(dbResponse);
      setFailedRuns(latestFailedRuns(jobsResponse));
    } catch (fetchError: unknown) {
      setError(errorMessage(fetchError, 'pgvector 데이터베이스 목록을 불러오지 못했습니다.'));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  useEffect(() => {
    const runId = localStorage.getItem(ACTIVE_JOB_KEY);
    const pendingFileName = localStorage.getItem(PENDING_FILE_KEY);
    const controller = new AbortController();
    const restore = runId
      ? dataSourceApi.getIngestionJob(runId, controller.signal)
      : dataSourceApi.listIngestionJobs(pendingFileName || undefined, controller.signal)
          .then(findRestorableIngestionJob);

    void restore
      .then((job) => {
        if (!job) {
          localStorage.removeItem(PENDING_FILE_KEY);
          return;
        }
        localStorage.setItem(ACTIVE_JOB_KEY, job.job_id);
        localStorage.removeItem(PENDING_FILE_KEY);
        const pipeline = pipelineFromIngestionJob(job);
        setActivePipelineRun(pipeline);
        if (pipeline.status === 'completed') {
          localStorage.removeItem(ACTIVE_JOB_KEY);
          void fetchData();
        } else if (pipeline.status === 'failed') {
          setFailedRuns((current) => [
            ...current.filter((run) => run.pipelineId !== pipeline.pipelineId),
            pipeline,
          ]);
        }
      })
      .catch((restoreError: unknown) => {
        if (!isAbortError(restoreError)) {
          localStorage.removeItem(ACTIVE_JOB_KEY);
          localStorage.removeItem(PENDING_FILE_KEY);
        }
      });

    return () => controller.abort();
  }, [fetchData]);

  const activePipelineId = activePipelineRun?.pipelineId;
  const activePipelineStatus = activePipelineRun?.status;

  useEffect(() => {
    if (
      !activePipelineId
      || !activePipelineStatus
      || !['queued', 'running'].includes(activePipelineStatus)
      || deletingPipelineId === activePipelineId
      || !isServerRun(activePipelineId)
    ) return undefined;

    const runId = activePipelineId;
    let stopped = false;
    let terminalHandled = false;
    const controller = new AbortController();

    const applyJob = (job: IngestionJobResponse): void => {
      if (stopped) return;
      setError(null);
      const pipeline = pipelineFromIngestionJob(job);
      setActivePipelineRun(pipeline);
      if (!terminalHandled && pipeline.status === 'completed') {
        terminalHandled = true;
        localStorage.removeItem(ACTIVE_JOB_KEY);
        setFailedRuns((current) => current.filter((run) => run.pipelineId !== runId));
        void fetchData();
      } else if (!terminalHandled && pipeline.status === 'failed') {
        terminalHandled = true;
        setFailedRuns((current) => [
          ...current.filter((run) => run.pipelineId !== runId),
          pipeline,
        ]);
      }
    };

    const observeJob = async (): Promise<void> => {
      try {
        const initial = await dataSourceApi.getIngestionJob(runId, controller.signal);
        if (stopped) return;
        applyJob(initial);
        if (initial.status === 'queued' || initial.status === 'running') {
          await dataSourceApi.streamIngestionJob(initial, applyJob, controller.signal);
        }
      } catch (streamError: unknown) {
        if (!stopped && !isAbortError(streamError)) {
          setError(errorMessage(streamError, '인덱싱 실행 상태 스트림에 연결하지 못했습니다.'));
        }
      }
    };

    void observeJob();
    return () => {
      stopped = true;
      controller.abort();
    };
  }, [activePipelineId, activePipelineStatus, deletingPipelineId, fetchData]);

  const startUploadPipeline = async (file: File, model: string, batchSize: number) => {
    setIsUploadOpen(false);
    setError(null);
    localStorage.setItem(PENDING_FILE_KEY, file.name);
    try {
      const uploadResponse = await dataSourceApi.uploadFile(file, true, model, batchSize);
      if (uploadResponse.error) throw new Error(uploadResponse.error);
      const job = uploadResponse.ingestion_job;
      if (!job) throw new Error('인덱싱 작업 ID를 받지 못했습니다.');
      localStorage.setItem(ACTIVE_JOB_KEY, job.job_id);
      localStorage.removeItem(PENDING_FILE_KEY);
      setActivePipelineRun(pipelineFromIngestionJob(job));
      setIsViewingTracker(true);
    } catch (uploadError: unknown) {
      localStorage.removeItem(PENDING_FILE_KEY);
      setError(errorMessage(uploadError, '인덱싱 작업을 시작하지 못했습니다.'));
      setIsViewingTracker(false);
    }
  };

  const deleteIndex = async (indexId: string) => {
    setDeletingIndexId(indexId);
    setError(null);
    try {
      await dataSourceApi.deleteIndex(indexId);
      await fetchData();
      setDeleteTarget(null);
    } catch (deleteIndexError: unknown) {
      setDeleteError(errorMessage(deleteIndexError, '컬렉션 삭제에 실패했습니다.'));
    } finally {
      setDeletingIndexId(null);
    }
  };

  const resumeActivePipeline = async () => {
    const run = activePipelineRun;
    if (!run || !isServerRun(run.pipelineId)) return;
    try {
      setError(null);
      const job = await dataSourceApi.resumeIngestionJob(run.pipelineId);
      const resumed = pipelineFromIngestionJob(job);
      const runningState: PipelineRunState = {
        ...resumed,
        status: 'running',
        error: null,
        modules: resumed.modules.map((module) => ({
          ...module,
          status: module.status === 'failed' ? 'waiting' : module.status,
        })),
      };
      localStorage.setItem(ACTIVE_JOB_KEY, job.job_id);
      setFailedRuns((current) => current.filter((candidate) => candidate.pipelineId !== job.job_id));
      setActivePipelineRun(runningState);
    } catch (resumeError: unknown) {
      setError(errorMessage(resumeError, '인덱싱 작업을 재개하지 못했습니다.'));
    }
  };

  const cancelActivePipeline = async () => {
    const run = activePipelineRun;
    if (!run || !isServerRun(run.pipelineId) || !['queued', 'running'].includes(run.status)) return;
    setIsCancellingPipeline(true);
    setError(null);
    try {
      const job = await dataSourceApi.cancelIngestionJob(run.pipelineId);
      const paused = pipelineFromIngestionJob(job);
      localStorage.setItem(ACTIVE_JOB_KEY, job.job_id);
      setFailedRuns((current) => current.filter((candidate) => candidate.pipelineId !== job.job_id));
      setActivePipelineRun(paused);
    } catch (cancelError: unknown) {
      setError(errorMessage(cancelError, '인덱싱 작업을 중단하지 못했습니다.'));
    } finally {
      setIsCancellingPipeline(false);
    }
  };

  const deletePipeline = async (run: PipelineRunState) => {
    setDeletingPipelineId(run.pipelineId);
    setError(null);
    try {
      await dataSourceApi.deleteIngestionJob(run.pipelineId);
      if (localStorage.getItem(ACTIVE_JOB_KEY) === run.pipelineId) {
        localStorage.removeItem(ACTIVE_JOB_KEY);
        localStorage.removeItem(PENDING_FILE_KEY);
      }
      setFailedRuns((current) => current.filter((candidate) => candidate.pipelineId !== run.pipelineId));
      if (activePipelineRun?.pipelineId === run.pipelineId) {
        setActivePipelineRun(null);
        setIsViewingTracker(false);
      }
      await fetchData();
      setDeleteTarget(null);
    } catch (deletePipelineError: unknown) {
      setDeleteError(errorMessage(deletePipelineError, '인덱싱 작업을 삭제하지 못했습니다.'));
    } finally {
      setDeletingPipelineId(null);
    }
  };

  const viewPipelineLog = async (index: VectorIndexInfo) => {
    try {
      const job = await dataSourceApi.getIngestionJobByIndex(index.index_id);
      setActivePipelineRun({ ...pipelineFromIngestionJob(job), isLiveUpload: false });
      setIsViewingTracker(true);
    } catch (viewLogError: unknown) {
      setError(errorMessage(viewLogError, '이 인덱스의 워크플로 실행 기록을 찾을 수 없습니다.'));
    }
  };

  const visibleFailedRuns = useMemo(() => failedRuns.filter(
    (run) => !activePipelineRun
      || !['queued', 'running', 'paused'].includes(activePipelineRun.status)
      || (run.pipelineId !== activePipelineRun.pipelineId && run.fileName !== activePipelineRun.fileName),
  ), [activePipelineRun, failedRuns]);

  return {
    indexes,
    dbStatus,
    isLoading,
    error,
    activePipelineRun,
    canResumeActivePipeline: Boolean(
      activePipelineRun
      && ['failed', 'paused'].includes(activePipelineRun.status)
      && isServerRun(activePipelineRun.pipelineId),
    ),
    isViewingTracker,
    isCancellingPipeline,
    deletingPipelineId,
    deletingIndexId,
    deleteTarget,
    deleteError,
    visibleFailedRuns,
    isUploadOpen,
    detailIndexId,
    searchTargetIndex,
    fetchData,
    openUpload: () => setIsUploadOpen(true),
    closeUpload: () => setIsUploadOpen(false),
    openDetail: setDetailIndexId,
    closeDetail: () => setDetailIndexId(null),
    openSearch: setSearchTargetIndex,
    closeSearch: () => setSearchTargetIndex(null),
    startUploadPipeline,
    viewFailedRunLog: (run: PipelineRunState) => {
      setActivePipelineRun(run);
      setIsViewingTracker(true);
    },
    viewPipelineLog,
    backFromTracker: () => {
      setIsViewingTracker(false);
      void fetchData();
    },
    resumeActivePipeline,
    cancelActivePipeline,
    requestDeleteIndex: (indexId: string) => {
      if (deletingIndexId) return;
      setDeleteError(null);
      setDeleteTarget({ type: 'index', indexId });
    },
    requestDeletePipeline: (run: PipelineRunState) => {
      if (!isServerRun(run.pipelineId)) return;
      setDeleteError(null);
      setDeleteTarget({ type: 'pipeline', run });
    },
    closeDeleteDialog: () => {
      setDeleteTarget(null);
      setDeleteError(null);
    },
    confirmDeleteTarget: () => {
      if (!deleteTarget) return;
      if (deleteTarget.type === 'index') void deleteIndex(deleteTarget.indexId);
      else void deletePipeline(deleteTarget.run);
    },
  };
}
