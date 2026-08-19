import { useEffect, useState, useCallback } from 'react';
import { Loader2 } from 'lucide-react';
import { DataSourcesSummary } from './components/DataSourcesSummary';
import { FileUploadModal } from './components/FileUploadModal';
import { IndexDetailModal } from './components/IndexDetailModal';
import { IndexSearchTester } from './components/IndexSearchTester';
import { PipelineTrackerView } from './components/PipelineTrackerView';
import type { PipelineRunState } from './pipelineTypes';
import { VectorIndexList } from './components/VectorIndexList';
import { dataSourceApi } from './services/dataSourceApi';
import { pipelineFromIngestionJob } from './workflowIngestion';
import type { DbStatusInfo, IngestionJobResponse, VectorIndexInfo } from './types';
import './data-sources.css';

const ACTIVE_JOB_KEY = 'ds_active_ingestion_job_id';
const PENDING_FILE_KEY = 'ds_pending_ingestion_file_name';

/**
 * Collects the latest failed pipeline run for each file.
 *
 * @param jobs - Ingestion jobs ordered from latest to oldest
 * @returns Failed pipeline states, with at most one state per file
 */
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

/**
 * Displays vector indexes, database status, and ingestion pipeline activity.
 *
 * Provides controls for uploading files, viewing index details, testing searches,
 * and monitoring, resuming, cancelling, or deleting ingestion pipelines.
 */
export function DataSourcesView() {
  const [indexes, setIndexes] = useState<VectorIndexInfo[]>([]);
  const [dbStatus, setDbStatus] = useState<DbStatusInfo | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Full-page active pipeline tracker
  const [activePipelineRun, setActivePipelineRun] = useState<PipelineRunState | null>(null);
  const [isViewingTracker, setIsViewingTracker] = useState(false);
  const [isCancellingPipeline, setIsCancellingPipeline] = useState(false);
  const [deletingPipelineId, setDeletingPipelineId] = useState<string | null>(null);

  const [failedRuns, setFailedRuns] = useState<PipelineRunState[]>([]);

  // Modals state
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [detailIndexId, setDetailIndexId] = useState<string | null>(null);
  const [searchTargetIndex, setSearchTargetIndex] = useState<VectorIndexInfo | null>(null);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [indexesRes, dbRes, jobsRes] = await Promise.all([
        dataSourceApi.listIndexes(),
        dataSourceApi.getDbStatus().catch(() => null),
        dataSourceApi.listIngestionJobs().catch(() => []),
      ]);
      setIndexes(indexesRes);
      if (dbRes) setDbStatus(dbRes);
      setFailedRuns(latestFailedRuns(jobsRes));
    } catch (err: any) {
      setError(err.message || 'pgvector 데이터베이스 목록을 불러오지 못했습니다.');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Restore a server-owned ingestion after navigation or a browser refresh.
  useEffect(() => {
    const runId = localStorage.getItem(ACTIVE_JOB_KEY);
    const pendingFileName = localStorage.getItem(PENDING_FILE_KEY);
    const controller = new AbortController();
    const restore = runId
      ? dataSourceApi.getIngestionJob(runId, controller.signal)
      : dataSourceApi.listIngestionJobs(pendingFileName || undefined, controller.signal)
          .then((jobs) => {
            if (pendingFileName) return jobs[0] ?? null;
            return jobs.find((job) => ['queued', 'running', 'paused'].includes(job.status)) ?? null;
          });

    restore
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
          fetchData();
        } else if (pipeline.status === 'failed') {
          setFailedRuns((existing) => [
            ...existing.filter((run) => run.pipelineId !== pipeline.pipelineId),
            pipeline,
          ]);
        }
      })
      .catch((err: any) => {
        if (err?.name !== 'AbortError') {
          localStorage.removeItem(ACTIVE_JOB_KEY);
          localStorage.removeItem(PENDING_FILE_KEY);
        }
      });

    return () => controller.abort();
  }, [fetchData]);

  // Polling observes the persisted run only. Closing this page does not own or
  // cancel the worker; a later visit reconnects with ACTIVE_JOB_KEY.
  useEffect(() => {
    if (
      !activePipelineRun
      || !['queued', 'running'].includes(activePipelineRun.status)
      || deletingPipelineId === activePipelineRun.pipelineId
    ) return;
    const runId = activePipelineRun.pipelineId;
    if (!runId.startsWith('run-')) return;

    let stopped = false;
    let requestInFlight = false;
    const controller = new AbortController();

    const refreshJob = async () => {
      if (requestInFlight || stopped) return;
      requestInFlight = true;
      try {
        const job = await dataSourceApi.getIngestionJob(runId, controller.signal);
        if (stopped) return;
        const pipeline = pipelineFromIngestionJob(job);
        setActivePipelineRun(pipeline);
        if (pipeline.status === 'completed') {
          localStorage.removeItem(ACTIVE_JOB_KEY);
          setFailedRuns((existing) => existing.filter((run) => run.pipelineId !== runId));
          await fetchData();
        } else if (pipeline.status === 'failed') {
          setFailedRuns((existing) => [
            ...existing.filter((run) => run.pipelineId !== runId),
            pipeline,
          ]);
        }
      } catch (err: any) {
        if (!stopped && err?.name !== 'AbortError') {
          setError(err.message || '인덱싱 실행 상태를 조회하지 못했습니다.');
        }
      } finally {
        requestInFlight = false;
      }
    };

    void refreshJob();
    const timer = window.setInterval(refreshJob, 1000);
    return () => {
      stopped = true;
      controller.abort();
      window.clearInterval(timer);
    };
  }, [activePipelineRun?.pipelineId, activePipelineRun?.status, deletingPipelineId, fetchData]);

  const handleViewFailedRunLog = (run: PipelineRunState) => {
    setActivePipelineRun(run);
    setIsViewingTracker(true);
  };

  const handleStartUploadPipeline = async (file: File, model: string, batchSize: number) => {
    setIsUploadOpen(false);
    setError(null);
    localStorage.setItem(PENDING_FILE_KEY, file.name);
    try {
      const uploadRes = await dataSourceApi.uploadFile(file, true, model, batchSize);
      if (uploadRes.error) {
        throw new Error(uploadRes.error);
      }
      const job = uploadRes.ingestion_job;
      if (!job) throw new Error('인덱싱 작업 ID를 받지 못했습니다.');
      localStorage.setItem(ACTIVE_JOB_KEY, job.job_id);
      localStorage.removeItem(PENDING_FILE_KEY);
      setActivePipelineRun(pipelineFromIngestionJob(job));
      setIsViewingTracker(true);
    } catch (err: any) {
      localStorage.removeItem(PENDING_FILE_KEY);
      setError(err.message || '인덱싱 작업을 시작하지 못했습니다.');
      setIsViewingTracker(false);
    }
  };

  const handleDeleteIndex = async (indexId: string) => {
    if (!window.confirm(`선택한 pgvector 컬렉션을 데이터베이스에서 영구 삭제하시겠습니까?\nID: ${indexId}`)) {
      return;
    }
    try {
      await dataSourceApi.deleteIndex(indexId);
      await fetchData();
    } catch (err: any) {
      alert(err.message || '컬렉션 삭제에 실패했습니다.');
    }
  };

  const handleResumeActivePipeline = async () => {
    if (!activePipelineRun?.pipelineId.startsWith('run-')) return;
    try {
      setError(null);
      const job = await dataSourceApi.resumeIngestionJob(activePipelineRun.pipelineId);
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
      setFailedRuns((existing) => existing.filter((run) => run.pipelineId !== job.job_id));
      setActivePipelineRun(runningState);
    } catch (err: any) {
      setError(err.message || '인덱싱 작업을 재개하지 못했습니다.');
    }
  };

  const handleCancelActivePipeline = async () => {
    if (
      !activePipelineRun?.pipelineId.startsWith('run-')
      || !['queued', 'running'].includes(activePipelineRun.status)
    ) return;
    setIsCancellingPipeline(true);
    setError(null);
    try {
      const job = await dataSourceApi.cancelIngestionJob(activePipelineRun.pipelineId);
      const paused = pipelineFromIngestionJob(job);
      localStorage.setItem(ACTIVE_JOB_KEY, job.job_id);
      setFailedRuns((existing) => existing.filter((run) => run.pipelineId !== job.job_id));
      setActivePipelineRun(paused);
    } catch (err: any) {
      setError(err.message || '인덱싱 작업을 중단하지 못했습니다.');
    } finally {
      setIsCancellingPipeline(false);
    }
  };

  const handleDeletePipeline = async (run: PipelineRunState) => {
    if (!run.pipelineId.startsWith('run-')) return;
    if (!window.confirm(
      `인덱싱 작업 기록과 생성 중인 부분 컬렉션을 삭제하시겠습니까?\n\n${run.fileName}\n원본 Excel 파일은 삭제되지 않습니다.`
    )) return;

    setDeletingPipelineId(run.pipelineId);
    setError(null);
    try {
      await dataSourceApi.deleteIngestionJob(run.pipelineId);
      if (localStorage.getItem(ACTIVE_JOB_KEY) === run.pipelineId) {
        localStorage.removeItem(ACTIVE_JOB_KEY);
        localStorage.removeItem(PENDING_FILE_KEY);
      }
      setFailedRuns((existing) => existing.filter((candidate) => candidate.pipelineId !== run.pipelineId));
      if (activePipelineRun?.pipelineId === run.pipelineId) {
        setActivePipelineRun(null);
        setIsViewingTracker(false);
      }
      await fetchData();
    } catch (err: any) {
      setError(err.message || '인덱싱 작업을 삭제하지 못했습니다.');
    } finally {
      setDeletingPipelineId(null);
    }
  };

  // If Full-Page Pipeline Tracker is active, render it exclusively
  if (activePipelineRun && isViewingTracker) {
    return (
      <div className="ds-page">
        <PipelineTrackerView
          pipeline={activePipelineRun}
          onBack={() => {
            setIsViewingTracker(false);
            fetchData();
          }}
          onResume={
            ['failed', 'paused'].includes(activePipelineRun.status) && activePipelineRun.pipelineId.startsWith('run-')
              ? handleResumeActivePipeline
              : undefined
          }
          onCancel={
            ['queued', 'running'].includes(activePipelineRun.status)
              ? handleCancelActivePipeline
              : undefined
          }
          onDelete={() => handleDeletePipeline(activePipelineRun)}
          isCancelling={isCancellingPipeline}
          isDeleting={deletingPipelineId === activePipelineRun.pipelineId}
        />
      </div>
    );
  }

  return (
    <div className="ds-page">
      {/* Summary KPI Cards */}
      <DataSourcesSummary indexes={indexes} dbStatus={dbStatus} />

      {error && <div className="ds-error-alert">{error}</div>}

      {/* Main Content Pane */}
      {isLoading ? (
        <div className="ds-loading-pane">
          <Loader2 className="ds-spin" size={32} />
          <span>pgvector 데이터베이스 동기화 중...</span>
        </div>
      ) : (
        <div className="ds-tab-content">
          <VectorIndexList
            indexes={indexes}
            isLoading={isLoading}
            activeRunningPipeline={activePipelineRun}
            failedRuns={failedRuns.filter(
              (run) => !activePipelineRun
                || !['queued', 'running', 'paused'].includes(activePipelineRun.status)
                || (
                  run.pipelineId !== activePipelineRun.pipelineId
                  && run.fileName !== activePipelineRun.fileName
                )
            )}
            onResumePipeline={() => setIsViewingTracker(true)}
            onViewFailedLog={handleViewFailedRunLog}
            onDeletePipeline={handleDeletePipeline}
            deletingPipelineId={deletingPipelineId}
            onRefresh={fetchData}
            onDetailClick={(id) => setDetailIndexId(id)}
            onSearchClick={(idx) => setSearchTargetIndex(idx)}
            onDeleteClick={handleDeleteIndex}
            onCreateClick={() => setIsUploadOpen(true)}
            onPipelineLogClick={async (idx) => {
              try {
                const job = await dataSourceApi.getIngestionJobByIndex(idx.index_id);
                setActivePipelineRun({
                  ...pipelineFromIngestionJob(job),
                  isLiveUpload: false,
                });
                setIsViewingTracker(true);
              } catch (err: any) {
                setError(err.message || '이 인덱스의 워크플로 실행 기록을 찾을 수 없습니다.');
              }
            }}
          />
        </div>
      )}

      {/* Modals */}
      {isUploadOpen && (
        <FileUploadModal
          onClose={() => setIsUploadOpen(false)}
          onStartPipeline={(file, model, batchSize) => {
            return handleStartUploadPipeline(file, model, batchSize);
          }}
        />
      )}

      {detailIndexId && (
        <IndexDetailModal
          indexId={detailIndexId}
          onClose={() => setDetailIndexId(null)}
        />
      )}

      {searchTargetIndex && (
        <IndexSearchTester
          indexId={searchTargetIndex.index_id}
          fileName={searchTargetIndex.file_name}
          model={searchTargetIndex.model}
          onClose={() => setSearchTargetIndex(null)}
        />
      )}
    </div>
  );
}
