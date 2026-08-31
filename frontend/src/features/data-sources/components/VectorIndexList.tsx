import { useState } from 'react';
import { Database, RefreshCw, Sparkles } from 'lucide-react';
import { Button } from '../../../shared/ui';
import type { PipelineRunState } from '../pipelineTypes';
import { dataSourceApi } from '../services/dataSourceApi';
import type { VectorIndexInfo } from '../types';
import {
  ActivePipelineRow,
  FailedPipelineRow,
  VectorIndexRow,
} from './VectorIndexRows';

interface VectorIndexListProps {
  indexes: VectorIndexInfo[];
  isLoading?: boolean;
  activeRunningPipelines?: PipelineRunState[];
  failedRuns?: PipelineRunState[];
  onViewPipeline?: (run: PipelineRunState) => void;
  onViewFailedLog?: (run: PipelineRunState) => void;
  onDeletePipeline?: (run: PipelineRunState) => void;
  deletingPipelineId?: string | null;
  deletingIndexId?: string | null;
  onRefresh?: () => void | Promise<void>;
  onDetailClick: (indexId: string) => void;
  onSearchClick: (index: VectorIndexInfo) => void;
  onDeleteClick: (indexId: string) => void;
  onCreateClick: () => void;
  onPipelineLogClick?: (index: VectorIndexInfo) => void;
}

const ACTIVE_PIPELINE_STATUSES = new Set<PipelineRunState['status']>([
  'queued',
  'running',
  'paused',
]);

/** Displays persisted pgvector collections alongside active and failed indexing runs. */
export function VectorIndexList({
  indexes,
  isLoading,
  activeRunningPipelines = [],
  failedRuns = [],
  onViewPipeline,
  onViewFailedLog,
  onDeletePipeline,
  deletingPipelineId,
  deletingIndexId,
  onRefresh,
  onDetailClick,
  onSearchClick,
  onDeleteClick,
  onCreateClick,
  onPipelineLogClick,
}: VectorIndexListProps) {
  const [editingIndexId, setEditingIndexId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState('');
  const [savingCompanyIndexId, setSavingCompanyIndexId] = useState<string | null>(null);
  const [companyEditError, setCompanyEditError] = useState('');

  const startEditCompany = (index: VectorIndexInfo) => {
    if (savingCompanyIndexId || deletingIndexId) return;
    setEditingIndexId(index.index_id);
    setEditingName(index.company_name || index.file_name?.replace(/\.[^/.]+$/, '') || '');
    setCompanyEditError('');
  };

  const cancelEdit = () => {
    if (savingCompanyIndexId) return;
    setEditingIndexId(null);
    setEditingName('');
    setCompanyEditError('');
  };

  const saveCompany = async (indexId: string) => {
    if (savingCompanyIndexId || deletingIndexId) return;
    const trimmed = editingName.trim();
    if (!trimmed) {
      setCompanyEditError('기업명을 입력해 주세요.');
      return;
    }

    setCompanyEditError('');
    setSavingCompanyIndexId(indexId);
    try {
      await dataSourceApi.updateIndexCompany(indexId, trimmed);
      await onRefresh?.();
      setEditingIndexId(null);
      setEditingName('');
    } catch (error: unknown) {
      setCompanyEditError(error instanceof Error ? error.message : '기업명 수정에 실패했습니다.');
    } finally {
      setSavingCompanyIndexId(null);
    }
  };

  const activePipelines = activeRunningPipelines.filter(
    (pipeline) => ACTIVE_PIPELINE_STATUSES.has(pipeline.status),
  );
  const hiddenIndexIds = new Set(
    [
      ...activePipelines,
      ...failedRuns,
    ]
      .filter((run): run is PipelineRunState => Boolean(run.targetIndexId))
      .map((run) => run.targetIndexId!),
  );
  const visibleIndexes = indexes.filter((index) => !hiddenIndexIds.has(index.index_id));
  const hasContent = visibleIndexes.length > 0 || failedRuns.length > 0 || activePipelines.length > 0;

  return (
    <div className="ds-panel">
      <div className="ds-panel__header">
        <div>
          <h3>PostgreSQL pgvector 컬렉션 목록</h3>
          <small>PostgreSQL 16 + pgvector native 컬렉션 (HNSW 코사인 유사도 인덱스)</small>
        </div>
        <div className="ds-panel__actions">
          {onRefresh && (
            <Button size="md" type="button" onClick={onRefresh} title="새로고침" disabled={isLoading}>
              <RefreshCw size={14} className={isLoading ? 'ds-spin' : ''} />
              <span>새로고침</span>
            </Button>
          )}
          <Button variant="primary" type="button" onClick={onCreateClick}>
            <Sparkles size={15} /> 새 엑셀 인덱싱
          </Button>
        </div>
      </div>

      {!hasContent ? (
        <div className="ds-empty-state">
          <Database size={44} />
          <h4>pgvector 데이터베이스에 등록된 컬렉션이 없습니다</h4>
          <p>엑셀 파일을 업로드하면 Luna VLM 표 구조 분석과 4필드 직렬화를 거쳐 pgvector로 벡터 인덱스가 즉시 생성됩니다.</p>
          <Button variant="primary" type="button" onClick={onCreateClick}>
            <Sparkles size={15} /> 새 엑셀 인덱싱 시작
          </Button>
        </div>
      ) : (
        <div className="ds-table-container">
          <table className="ds-table ds-index-table">
            <thead>
              <tr>
                <th className="ds-index-table__id">컬렉션 ID</th>
                <th>대상 데이터셋</th>
                <th className="ds-index-table__company">기업명 (Company)</th>
                <th className="ds-index-table__model">임베딩 모델</th>
                <th className="ds-index-table__dimension">차원</th>
                <th className="ds-index-table__chunks">저장된 청크 수</th>
                <th className="ds-index-table__storage">스토리지</th>
                <th className="ds-index-table__created">생성일시</th>
                <th className="ds-index-table__actions ds-actions-col ds-text-right">작업</th>
              </tr>
            </thead>
            <tbody>
              {activePipelines.map((pipeline) => (
                <ActivePipelineRow
                  key={pipeline.pipelineId}
                  pipeline={pipeline}
                  deleting={deletingPipelineId === pipeline.pipelineId}
                  onView={onViewPipeline}
                  onDelete={onDeletePipeline}
                />
              ))}
              {failedRuns.map((run) => (
                <FailedPipelineRow
                  key={run.pipelineId}
                  run={run}
                  deleting={deletingPipelineId === run.pipelineId}
                  onViewLog={onViewFailedLog}
                  onDelete={onDeletePipeline}
                />
              ))}
              {visibleIndexes.map((index) => (
                <VectorIndexRow
                  key={index.index_id}
                  index={index}
                  editing={editingIndexId === index.index_id}
                  editingName={editingName}
                  editError={editingIndexId === index.index_id ? companyEditError : ''}
                  saving={savingCompanyIndexId === index.index_id}
                  deleting={deletingIndexId === index.index_id}
                  editLocked={Boolean(savingCompanyIndexId) || Boolean(deletingIndexId)}
                  onEditingNameChange={setEditingName}
                  onStartEdit={() => startEditCompany(index)}
                  onCancelEdit={cancelEdit}
                  onSave={() => void saveCompany(index.index_id)}
                  onPipelineLog={onPipelineLogClick}
                  onSearch={onSearchClick}
                  onDetail={onDetailClick}
                  onDelete={onDeleteClick}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
