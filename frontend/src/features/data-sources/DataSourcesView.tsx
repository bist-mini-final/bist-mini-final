import { Loader2 } from 'lucide-react';
import { ConfirmDialog } from '../../shared/ui';
import { DataSourcesSummary } from './components/DataSourcesSummary';
import { FileUploadModal } from './components/FileUploadModal';
import { IndexDetailModal } from './components/IndexDetailModal';
import { IndexSearchTester } from './components/IndexSearchTester';
import { PipelineTrackerView } from './components/PipelineTrackerView';
import { VectorIndexList } from './components/VectorIndexList';
import { useDataSourcesController } from './useDataSourcesController';
import './data-sources.css';
import './components/PipelineTracker.css';

export { findRestorableIngestionJob } from './useDataSourcesController';

/** Renders the data sources workspace from the state owned by its controller hook. */
export function DataSourcesView() {
  const controller = useDataSourcesController();
  const {
    indexes,
    dbStatus,
    isLoading,
    error,
    activePipelineRuns,
    activePipelineRun,
    canResumeActivePipeline,
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
  } = controller;

  const deleteDialog = (
    <ConfirmDialog
      open={deleteTarget !== null}
      tone="danger"
      title={deleteTarget?.type === 'pipeline' ? '인덱싱 작업을 삭제하시겠습니까?' : '컬렉션을 삭제하시겠습니까?'}
      description={deleteTarget?.type === 'pipeline'
        ? '작업 기록과 생성 중인 부분 컬렉션이 삭제됩니다. 원본 Excel 파일은 유지됩니다.'
        : '선택한 pgvector 컬렉션이 데이터베이스에서 영구 삭제됩니다.'}
      detail={deleteTarget?.type === 'pipeline'
        ? deleteTarget.run.fileName
        : deleteTarget?.type === 'index' ? `Collection ID · ${deleteTarget.indexId}` : undefined}
      confirmLabel="삭제"
      busy={Boolean(deletingIndexId || deletingPipelineId)}
      error={deleteError}
      onClose={controller.closeDeleteDialog}
      onConfirm={controller.confirmDeleteTarget}
    />
  );

  if (activePipelineRun && isViewingTracker) {
    return (
      <div className="ds-page">
        <h1 className="page-visually-hidden">데이터 적재 작업</h1>
        <PipelineTrackerView
          pipeline={activePipelineRun}
          onBack={controller.backFromTracker}
          onResume={canResumeActivePipeline ? controller.resumeActivePipeline : undefined}
          onCancel={['queued', 'running'].includes(activePipelineRun.status)
            ? controller.cancelActivePipeline
            : undefined}
          onDelete={() => controller.requestDeletePipeline(activePipelineRun)}
          isCancelling={isCancellingPipeline}
          isDeleting={deletingPipelineId === activePipelineRun.pipelineId}
        />
        {deleteDialog}
      </div>
    );
  }

  return (
    <div className="ds-page">
      <h1 className="page-visually-hidden">데이터 소스</h1>
      <DataSourcesSummary indexes={indexes} dbStatus={dbStatus} />
      {error && <div className="ds-error-alert" role="alert">{error}</div>}

      {isLoading ? (
        <div className="ds-loading-pane" role="status" aria-live="polite">
          <Loader2 className="ds-spin" size={32} />
          <span>pgvector 데이터베이스 동기화 중...</span>
        </div>
      ) : (
        <div className="ds-tab-content">
          <VectorIndexList
            indexes={indexes}
            isLoading={isLoading}
            activeRunningPipelines={activePipelineRuns}
            failedRuns={visibleFailedRuns}
            onViewPipeline={controller.viewPipelineRun}
            onViewFailedLog={controller.viewFailedRunLog}
            onDeletePipeline={controller.requestDeletePipeline}
            deletingPipelineId={deletingPipelineId}
            deletingIndexId={deletingIndexId}
            onRefresh={controller.fetchData}
            onDetailClick={controller.openDetail}
            onSearchClick={controller.openSearch}
            onDeleteClick={controller.requestDeleteIndex}
            onCreateClick={controller.openUpload}
            onPipelineLogClick={(index) => void controller.viewPipelineLog(index)}
          />
        </div>
      )}

      {isUploadOpen && (
        <FileUploadModal
          onClose={controller.closeUpload}
          onStartPipeline={controller.startUploadPipeline}
        />
      )}
      {detailIndexId && <IndexDetailModal indexId={detailIndexId} onClose={controller.closeDetail} />}
      {searchTargetIndex && (
        <IndexSearchTester
          indexId={searchTargetIndex.index_id}
          fileName={searchTargetIndex.file_name}
          model={searchTargetIndex.model}
          onClose={controller.closeSearch}
        />
      )}
      {deleteDialog}
    </div>
  );
}
