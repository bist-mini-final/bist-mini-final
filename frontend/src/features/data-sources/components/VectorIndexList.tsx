import { useState } from 'react';
import {
  AlertCircle,
  Building2,
  Check,
  Clock,
  Cpu,
  Database,
  Edit2,
  Eye,
  Layers,
  Pause,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react';
import { Button, IconButton } from '../../../shared/ui';
import type { VectorIndexInfo } from '../types';
import type { PipelineRunState } from '../pipelineTypes';
import { dataSourceApi } from '../services/dataSourceApi';

interface VectorIndexListProps {
  indexes: VectorIndexInfo[];
  isLoading?: boolean;
  activeRunningPipeline?: PipelineRunState | null;
  failedRuns?: PipelineRunState[];
  onResumePipeline?: () => void;
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

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    const hh = String(d.getHours()).padStart(2, '0');
    const min = String(d.getMinutes()).padStart(2, '0');
    return `${yyyy}.${mm}.${dd} ${hh}:${min}`;
  } catch {
    return iso;
  }
}

/**
 * Displays pgvector collections alongside active and failed indexing runs.
 *
 * @param indexes - Vector indexes available for display
 * @param isLoading - Whether collection data is currently loading
 * @param activeRunningPipeline - A queued, running, or paused indexing pipeline
 * @param failedRuns - Indexing pipelines that failed or were interrupted
 * @param onRefresh - Callback invoked to refresh the collection list
 * @param onCreateClick - Callback invoked to start a new indexing operation
 * @returns The rendered collection list and indexing status
 */
export function VectorIndexList({
  indexes,
  isLoading,
  activeRunningPipeline,
  failedRuns = [],
  onResumePipeline,
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

  const startEditCompany = (idx: VectorIndexInfo) => {
    if (savingCompanyIndexId || deletingIndexId) return;
    setEditingIndexId(idx.index_id);
    setEditingName(idx.company_name || idx.file_name?.replace(/\.[^/.]+$/, '') || '');
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
      setCompanyEditError(
        error instanceof Error ? error.message : '기업명 수정에 실패했습니다.',
      );
    } finally {
      setSavingCompanyIndexId(null);
    }
  };

  const isPipelineActive = activeRunningPipeline
    && ['queued', 'running', 'paused'].includes(activeRunningPipeline.status);
  const isPipelinePaused = activeRunningPipeline?.status === 'paused';
  const hiddenIndexIds = new Set(
    [
      ...(isPipelineActive && activeRunningPipeline ? [activeRunningPipeline] : []),
      ...failedRuns,
    ]
      .filter((run): run is PipelineRunState => Boolean(run?.targetIndexId))
      .map((run) => run.targetIndexId!),
  );
  const visibleIndexes = indexes.filter((index) => !hiddenIndexIds.has(index.index_id));
  const hasContent =
    visibleIndexes.length > 0 ||
    failedRuns.length > 0 ||
    isPipelineActive;

  return (
    <div className="ds-panel">
      <div className="ds-panel__header">
        <div>
          <h3>PostgreSQL pgvector 컬렉션 목록</h3>
          <small>PostgreSQL 16 + pgvector native 컬렉션 (HNSW 코사인 유사도 인덱스)</small>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          {onRefresh && (
            <Button
              size="md"
              type="button"
              onClick={onRefresh}
              title="새로고침"
              disabled={isLoading}
            >
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
          <table className="ds-table">
            <thead>
              <tr>
                <th style={{ width: '120px' }}>컬렉션 ID</th>
                <th>대상 데이터셋</th>
                <th style={{ width: '200px' }}>기업명 (Company)</th>
                <th style={{ width: '150px' }}>임베딩 모델</th>
                <th style={{ width: '70px' }}>차원</th>
                <th style={{ width: '130px' }}>저장된 청크 수</th>
                <th style={{ width: '120px' }}>스토리지</th>
                <th style={{ width: '130px' }}>생성일시</th>
                <th className="ds-actions-col ds-text-right" style={{ width: '270px' }}>작업</th>
              </tr>
            </thead>
            <tbody>
              {/* ── Running pipeline row ── */}
              {activeRunningPipeline && isPipelineActive && (
                <tr style={{
                  background: isPipelinePaused ? 'rgba(245, 158, 11, 0.08)' : 'rgba(34, 197, 94, 0.07)',
                  borderLeft: `3px solid ${isPipelinePaused ? '#d97706' : '#16a34a'}`,
                }}>
                  <td className="ds-font-mono ds-id-cell" style={{ color: isPipelinePaused ? '#b45309' : '#16a34a', fontWeight: 600 }}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '5px' }}>
                      {isPipelinePaused
                        ? <Pause size={12} style={{ color: '#b45309' }} />
                        : <RefreshCw size={12} className="ds-spin" style={{ color: '#16a34a' }} />}
                      {isPipelinePaused
                        ? '중단됨'
                        : activeRunningPipeline.status === 'queued'
                          ? '대기 중'
                          : '인덱싱 중'}
                    </span>
                  </td>
                  <td>
                    <div style={{ fontWeight: 650, color: '#0f172a' }}>{activeRunningPipeline.fileName}</div>
                    <div style={{ fontSize: '11px', color: isPipelinePaused ? '#92400e' : '#166534', marginTop: '2px' }}>
                      {isPipelinePaused
                        ? '완료된 모듈 결과를 보존한 채 사용자 중단됨'
                        : activeRunningPipeline.status === 'queued'
                        ? '서버 작업 큐에서 실행 대기 중'
                        : activeRunningPipeline.modules[activeRunningPipeline.currentStageIndex]?.name || '파이프라인 실행 중...'}
                    </div>
                  </td>
                  <td>
                    <span className="ds-badge ds-badge--gray" style={{ display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                      {isPipelinePaused ? <Pause size={11} /> : <Sparkles size={11} />}
                      {isPipelinePaused ? '재개 가능' : '자동 분석 중'}
                    </span>
                  </td>
                  <td>
                    <span className="ds-badge ds-badge--blue">{activeRunningPipeline.model}</span>
                  </td>
                  <td style={{ color: '#94a3b8' }}>—</td>
                  <td>
                    <span style={{ color: isPipelinePaused ? '#b45309' : '#16a34a', fontWeight: 600 }}>
                      {activeRunningPipeline.modules[activeRunningPipeline.currentStageIndex]?.batchProgress
                        ? `${activeRunningPipeline.modules[activeRunningPipeline.currentStageIndex].batchProgress!.completed}/${activeRunningPipeline.modules[activeRunningPipeline.currentStageIndex].batchProgress!.total} 배치`
                        : `${Math.round(activeRunningPipeline.progressPercent)}% (${activeRunningPipeline.currentStageIndex + 1}/${activeRunningPipeline.modules?.length ?? 5}단계)`}
                    </span>
                  </td>
                  <td>
                    <span className="ds-badge ds-badge--green" style={{
                      background: isPipelinePaused ? '#fef3c7' : '#dcfce7',
                      color: isPipelinePaused ? '#92400e' : '#166534',
                    }}>
                      {isPipelinePaused
                        ? '재개 대기'
                        : activeRunningPipeline.status === 'queued'
                          ? '배치 큐 대기'
                          : 'pgvector 적재 중'}
                    </span>
                  </td>
                  <td style={{ color: '#64748b', fontSize: '12px' }}>
                    {Math.round(activeRunningPipeline.elapsedSeconds)}초 경과
                  </td>
                  <td className="ds-actions-col ds-text-right">
                    <div style={{ display: 'inline-flex', gap: '6px', alignItems: 'center' }}>
                      <Button
                        variant="primary"
                        size="sm"
                        type="button"
                        onClick={onResumePipeline}
                        title={isPipelinePaused ? '중단된 파이프라인 확인 및 재개' : '실시간 파이프라인 HUD 및 모듈 로그로 재진입'}
                      >
                        <Layers size={13} /> 진행상황 / 모듈 로그
                      </Button>
                      {onDeletePipeline && (
                        <Button
                          variant="danger"
                          size="sm"
                          type="button"
                          onClick={() => onDeletePipeline(activeRunningPipeline)}
                          disabled={deletingPipelineId === activeRunningPipeline.pipelineId}
                          title="작업과 생성 중인 부분 컬렉션 삭제"
                        >
                          {deletingPipelineId === activeRunningPipeline.pipelineId
                            ? <RefreshCw size={12} className="ds-spin" />
                            : <Trash2 size={12} />}
                          작업 삭제
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              )}

              {/* ── Failed / interrupted pipeline rows ── */}
              {failedRuns.map((run) => {
                const failedStageLabel = run.modules?.find((m) => (m.status as any) === 'failed' || m.status === 'running')?.name
                  || run.modules?.[run.currentStageIndex]?.name
                  || '알 수 없는 단계';
                return (
                  <tr key={run.pipelineId} style={{ background: 'rgba(239, 68, 68, 0.05)', borderLeft: '3px solid #dc2626' }}>
                    <td className="ds-font-mono ds-id-cell" style={{ color: '#dc2626', fontWeight: 600 }}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '5px' }}>
                        <AlertCircle size={12} style={{ color: '#dc2626', flexShrink: 0 }} />
                        실패
                      </span>
                    </td>
                    <td>
                      <div style={{ fontWeight: 650, color: '#0f172a' }}>{run.fileName}</div>
                      <div style={{ fontSize: '11px', color: '#991b1b', marginTop: '2px', maxWidth: '320px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}                   title={run.error ?? undefined}>
                        ⚠️ {run.error || '알 수 없는 오류'}
                      </div>
                    </td>
                    <td>
                      <span className="ds-badge ds-badge--gray" style={{ background: '#fee2e2', color: '#991b1b' }}>
                        실패 단계: {failedStageLabel.split('(')[0].trim()}
                      </span>
                    </td>
                    <td>
                      <span className="ds-badge ds-badge--blue">{run.model}</span>
                    </td>
                    <td style={{ color: '#94a3b8' }}>—</td>
                    <td style={{ color: '#94a3b8', fontSize: '12px' }}>—</td>
                    <td style={{ color: '#94a3b8', fontSize: '12px' }}>—</td>
                    <td style={{ color: '#64748b', fontSize: '12px' }}>
                      {Math.round(run.elapsedSeconds || 0)}초 경과
                    </td>
                    <td className="ds-actions-col ds-text-right">
                      <div style={{ display: 'inline-flex', gap: '6px', alignItems: 'center' }}>
                        <Button
                          variant="danger"
                          size="sm"
                          type="button"
                          onClick={() => onViewFailedLog?.(run)}
                          title="실패 단계 및 모듈 로그 확인"
                        >
                          <Layers size={12} /> 실패 로그
                        </Button>
                        {onDeletePipeline && (
                          <Button
                            variant="danger"
                            size="sm"
                            type="button"
                            onClick={() => onDeletePipeline(run)}
                            disabled={deletingPipelineId === run.pipelineId}
                            title="실패 작업 기록과 부분 컬렉션 삭제"
                          >
                            {deletingPipelineId === run.pipelineId
                              ? <RefreshCw size={12} className="ds-spin" />
                              : <Trash2 size={12} />}
                            삭제
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}

              {/* ── Successful index rows ── */}
              {visibleIndexes.map((idx) => {
                const isEditingThis = editingIndexId === idx.index_id;
                const isSavingThis = savingCompanyIndexId === idx.index_id;
                const isDeletingThis = deletingIndexId === idx.index_id;
                const isRowBusy = isSavingThis || isDeletingThis;
                const companyDisplay = idx.company_name || '';
                const companyMessageId = companyEditError
                  ? `company-error-${idx.index_id}`
                  : isSavingThis
                    ? `company-status-${idx.index_id}`
                    : undefined;

                return (
                  <tr
                    key={idx.index_id}
                    className={`ds-index-row${isSavingThis ? ' ds-index-row--updating' : ''}${isDeletingThis ? ' ds-index-row--deleting' : ''}`}
                    aria-busy={isRowBusy || undefined}
                  >
                    <td className="ds-font-mono ds-id-cell" style={{ whiteSpace: 'nowrap' }}>
                      <span title={idx.index_id}>{idx.index_id.slice(0, 10)}...</span>
                    </td>
                    <td style={{ whiteSpace: 'nowrap', fontWeight: 650, color: '#0f172a' }}>
                      {idx.file_name || 'Dataset'}
                    </td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <div className="ds-company-cell">
                        {isEditingThis ? (
                          <div className="ds-company-editor">
                            <div className="ds-company-inline-form">
                              <input
                                type="text"
                                className="ds-company-inline-input"
                                value={editingName}
                                onChange={(e) => setEditingName(e.target.value)}
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter') void saveCompany(idx.index_id);
                                  else if (e.key === 'Escape') cancelEdit();
                                }}
                                placeholder="기업명 입력..."
                                aria-label="기업명"
                                aria-invalid={Boolean(companyEditError)}
                                aria-describedby={companyMessageId}
                                autoFocus
                                disabled={isSavingThis}
                              />
                              <IconButton
                                variant="primary"
                                size="sm"
                                aria-label="기업명 저장"
                                type="button"
                                className="ds-company-inline-save"
                                title="저장 (Enter)"
                                onClick={() => void saveCompany(idx.index_id)}
                                disabled={isSavingThis}
                                busy={isSavingThis}
                              >
                                {isSavingThis ? <RefreshCw className="ds-spin" size={12} /> : <Check size={12} />}
                              </IconButton>
                              <IconButton
                                variant="ghost"
                                size="sm"
                                aria-label="기업명 수정 취소"
                                type="button"
                                className="ds-company-inline-cancel"
                                title="취소 (Esc)"
                                onClick={cancelEdit}
                                disabled={isSavingThis}
                              >
                                <X size={12} />
                              </IconButton>
                            </div>
                            {companyEditError && (
                              <small id={`company-error-${idx.index_id}`} className="ds-company-edit-error" role="alert">
                                {companyEditError}
                              </small>
                            )}
                            {isSavingThis && (
                              <small
                                id={`company-status-${idx.index_id}`}
                                className="ds-company-operation-status"
                                role="status"
                                aria-live="polite"
                              >
                                <RefreshCw className="ds-spin" size={11} />
                                기업명 변경 중...
                              </small>
                            )}
                          </div>
                        ) : (
                          <>
                            <button
                              type="button"
                              className={`ds-company-badge ${!companyDisplay ? 'ds-company-badge--empty' : ''}`}
                              title="클릭하여 기업명 수정"
                              aria-label={`${companyDisplay || '미지정'} 기업명 수정`}
                              onClick={() => startEditCompany(idx)}
                              disabled={Boolean(savingCompanyIndexId) || Boolean(deletingIndexId)}
                            >
                              <Building2 size={12} style={{ color: companyDisplay ? '#166534' : '#94a3b8' }} />
                              <span>{companyDisplay || '+ 기업명 입력'}</span>
                            </button>
                            <IconButton
                              variant="ghost"
                              size="sm"
                              aria-label="기업명 수정"
                              type="button"
                              className="ds-company-edit-btn"
                              title="기업명 수정"
                              onClick={() => startEditCompany(idx)}
                              disabled={Boolean(savingCompanyIndexId) || Boolean(deletingIndexId)}
                            >
                              <Edit2 size={12} />
                            </IconButton>
                          </>
                        )}
                      </div>
                    </td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <span className="ds-model-badge" title={idx.model}>
                        {idx.model}
                      </span>
                    </td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <span className="ds-dim-pill">{idx.dimension}D</span>
                    </td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <div className="ds-chunk-block">
                        <div className="ds-chunk-primary">
                          <Layers size={13} style={{ color: '#0f766e' }} />
                          <span>{idx.document_count.toLocaleString()}개</span>
                        </div>
                        {idx.duration_seconds !== undefined && idx.duration_seconds !== null && (
                          <div className="ds-chunk-subtext">
                            ⏱️ {idx.duration_seconds}s {idx.estimated_cost_usd ? `· $${idx.estimated_cost_usd.toFixed(4)}` : ''}
                          </div>
                        )}
                      </div>
                    </td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <span className="ds-badge ds-badge--green" title="PostgreSQL 16 pgvector HNSW">
                        PostgreSQL + pgvector
                      </span>
                    </td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <span className="ds-time-text">
                        <Clock size={12} /> {formatDate(idx.created_at)}
                      </span>
                    </td>
                    <td className="ds-actions-col ds-text-right" style={{ whiteSpace: 'nowrap' }}>
                      {isDeletingThis ? (
                        <div className="ds-row-operation ds-row-operation--danger" role="status" aria-live="polite">
                          <RefreshCw className="ds-spin" size={13} />
                          <span>데이터 삭제 중...</span>
                        </div>
                      ) : (
                        <div className="ds-actions-row">
                        <Button
                          size="sm"
                          type="button"
                          title="4대 모듈 파이프라인 실행 로그 및 세부 단계 확인"
                          onClick={() => onPipelineLogClick?.(idx)}
                          disabled={isSavingThis}
                        >
                          <Cpu size={13} />
                          <span>모듈 로그</span>
                        </Button>
                        <Button
                          variant="primary"
                          size="sm"
                          type="button"
                          title="유사도 검색 테스트"
                          onClick={() => onSearchClick(idx)}
                          disabled={isSavingThis}
                        >
                          <Search size={13} />
                          <span>검색 테스트</span>
                        </Button>
                        <Button
                          size="sm"
                          type="button"
                          title="청크 및 메타데이터 상세 보기"
                          onClick={() => onDetailClick(idx.index_id)}
                          disabled={isSavingThis}
                        >
                          <Eye size={13} />
                          <span>상세</span>
                        </Button>
                        <IconButton
                          variant="danger"
                          size="sm"
                          aria-label="인덱스 삭제"
                          type="button"
                          title="인덱스 삭제"
                          onClick={() => onDeleteClick(idx.index_id)}
                          disabled={Boolean(deletingIndexId) || isSavingThis}
                        >
                          <Trash2 size={13} />
                        </IconButton>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
