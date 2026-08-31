import {
  AlertCircle,
  Building2,
  Check,
  Clock,
  Cpu,
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
import { useEffect, useRef } from 'react';
import { Button, IconButton } from '../../../shared/ui';
import type { PipelineRunState } from '../pipelineTypes';
import type { VectorIndexInfo } from '../types';

function formatDate(iso: string): string {
  try {
    const date = new Date(iso);
    const yyyy = date.getFullYear();
    const mm = String(date.getMonth() + 1).padStart(2, '0');
    const dd = String(date.getDate()).padStart(2, '0');
    const hh = String(date.getHours()).padStart(2, '0');
    const min = String(date.getMinutes()).padStart(2, '0');
    return `${yyyy}.${mm}.${dd} ${hh}:${min}`;
  } catch {
    return iso;
  }
}

interface ActivePipelineRowProps {
  readonly compact?: boolean;
  readonly pipeline: PipelineRunState;
  readonly deleting: boolean;
  readonly onView?: (run: PipelineRunState) => void;
  readonly onDelete?: (run: PipelineRunState) => void;
}

export function ActivePipelineRow({
  compact = false,
  pipeline,
  deleting,
  onView,
  onDelete,
}: ActivePipelineRowProps) {
  const isPaused = pipeline.status === 'paused';
  const activeModule = pipeline.modules[pipeline.currentStageIndex];

  if (compact) {
    return (
      <tr className={`ds-pipeline-table-row ds-pipeline-table-row--${isPaused ? 'paused' : 'active'}`}>
        <td className="ds-mobile-list-cell" colSpan={9}>
          <div className="ds-mobile-list-row">
            <span
              className={`ds-mobile-list-state ${isPaused ? 'is-paused' : 'is-running'}`}
              aria-label={isPaused ? '중단됨' : pipeline.status === 'queued' ? '대기 중' : '인덱싱 중'}
            >
              {isPaused ? <Pause size={13} /> : <RefreshCw size={13} className="ds-spin" />}
            </span>
            <strong className="ds-mobile-list-title" title={pipeline.fileName}>{pipeline.fileName}</strong>
            <span className="ds-mobile-list-meta">
              {activeModule?.batchProgress
                ? `${activeModule.batchProgress.completed}/${activeModule.batchProgress.total}`
                : `${Math.round(pipeline.progressPercent)}%`}
            </span>
            <div className="ds-mobile-list-actions">
              <IconButton variant="primary" size="sm" type="button" aria-label="진행상황 및 모듈 로그" onClick={() => onView?.(pipeline)}>
                <Layers size={13} />
              </IconButton>
              {onDelete && (
                <IconButton variant="danger" size="sm" type="button" aria-label="인덱싱 작업 삭제" onClick={() => onDelete(pipeline)} disabled={deleting}>
                  {deleting ? <RefreshCw size={12} className="ds-spin" /> : <Trash2 size={12} />}
                </IconButton>
              )}
            </div>
          </div>
        </td>
      </tr>
    );
  }

  return (
    <tr className={`ds-pipeline-table-row ds-pipeline-table-row--${isPaused ? 'paused' : 'active'}`}>
      <td className="ds-id-cell ds-pipeline-table-row__status" data-label="상태">
        <span className="ds-inline-icon-label">
          {isPaused
            ? <Pause size={12} />
            : <RefreshCw size={12} className="ds-spin" />}
          {isPaused ? '중단됨' : pipeline.status === 'queued' ? '대기 중' : '인덱싱 중'}
        </span>
      </td>
      <td data-label="대상 데이터셋">
        <div className="ds-table-dataset-name">{pipeline.fileName}</div>
        <div className="ds-pipeline-table-row__description">
          {isPaused
            ? '완료된 모듈 결과를 보존한 채 사용자 중단됨'
            : pipeline.status === 'queued'
              ? '서버 작업 큐에서 실행 대기 중'
              : activeModule?.name || '파이프라인 실행 중...'}
        </div>
      </td>
      <td data-label="기업명">
        <span className="ds-badge ds-badge--gray ds-inline-icon-label">
          {isPaused ? <Pause size={11} /> : <Sparkles size={11} />}
          {isPaused ? '재개 가능' : '자동 분석 중'}
        </span>
      </td>
      <td data-label="임베딩 모델"><span className="ds-badge ds-badge--blue">{pipeline.model}</span></td>
      <td className="ds-table-cell--muted" data-label="차원">—</td>
      <td className="ds-pipeline-table-row__progress" data-label="진행률">
        {activeModule?.batchProgress
          ? `${activeModule.batchProgress.completed}/${activeModule.batchProgress.total} 배치`
          : `${Math.round(pipeline.progressPercent)}% (${pipeline.currentStageIndex + 1}/${pipeline.modules.length || 5}단계)`}
      </td>
      <td data-label="스토리지">
        <span className={`ds-badge ds-pipeline-table-row__storage ${isPaused ? 'is-paused' : ''}`}>
          {isPaused ? '재개 대기' : pipeline.status === 'queued' ? '배치 큐 대기' : 'pgvector 적재 중'}
        </span>
      </td>
      <td className="ds-table-cell--time" data-label="경과 시간">{Math.round(pipeline.elapsedSeconds)}초 경과</td>
      <td className="ds-actions-col ds-text-right" data-label="작업">
        <div className="ds-actions-row">
          <Button
            variant="primary"
            size="sm"
            type="button"
            onClick={() => onView?.(pipeline)}
            title={isPaused ? '중단된 파이프라인 확인 및 재개' : '실시간 파이프라인 HUD 및 모듈 로그로 재진입'}
          >
            <Layers size={13} /> 진행상황 / 모듈 로그
          </Button>
          {onDelete && (
            <Button
              variant="danger"
              size="sm"
              type="button"
              onClick={() => onDelete(pipeline)}
              disabled={deleting}
              title="작업과 생성 중인 부분 컬렉션 삭제"
            >
              {deleting ? <RefreshCw size={12} className="ds-spin" /> : <Trash2 size={12} />}
              작업 삭제
            </Button>
          )}
        </div>
      </td>
    </tr>
  );
}

interface FailedPipelineRowProps {
  readonly compact?: boolean;
  readonly run: PipelineRunState;
  readonly deleting: boolean;
  readonly onViewLog?: (run: PipelineRunState) => void;
  readonly onDelete?: (run: PipelineRunState) => void;
}

export function FailedPipelineRow({
  compact = false,
  run,
  deleting,
  onViewLog,
  onDelete,
}: FailedPipelineRowProps) {
  const failedStageLabel = run.modules.find((module) =>
    module.status === 'failed' || module.status === 'running')?.name
    || run.modules[run.currentStageIndex]?.name
    || '알 수 없는 단계';

  if (compact) {
    return (
      <tr className="ds-pipeline-table-row ds-pipeline-table-row--failed">
        <td className="ds-mobile-list-cell" colSpan={9}>
          <div className="ds-mobile-list-row">
            <span className="ds-mobile-list-state is-failed" aria-label="인덱싱 실패"><AlertCircle size={13} /></span>
            <strong className="ds-mobile-list-title" title={`${run.fileName} · ${run.error || failedStageLabel}`}>{run.fileName}</strong>
            <span className="ds-mobile-list-meta is-failed">실패</span>
            <div className="ds-mobile-list-actions">
              <IconButton variant="danger" size="sm" type="button" aria-label="실패 로그 확인" onClick={() => onViewLog?.(run)}>
                <Layers size={12} />
              </IconButton>
              {onDelete && (
                <IconButton variant="danger" size="sm" type="button" aria-label="실패 작업 삭제" onClick={() => onDelete(run)} disabled={deleting}>
                  {deleting ? <RefreshCw size={12} className="ds-spin" /> : <Trash2 size={12} />}
                </IconButton>
              )}
            </div>
          </div>
        </td>
      </tr>
    );
  }

  return (
    <tr className="ds-pipeline-table-row ds-pipeline-table-row--failed">
      <td className="ds-id-cell ds-pipeline-table-row__status" data-label="상태">
        <span className="ds-inline-icon-label"><AlertCircle size={12} />실패</span>
      </td>
      <td data-label="대상 데이터셋">
        <div className="ds-table-dataset-name">{run.fileName}</div>
        <div className="ds-pipeline-table-row__error" title={run.error ?? undefined}>
          ⚠️ {run.error || '알 수 없는 오류'}
        </div>
      </td>
      <td data-label="실패 단계">
        <span className="ds-badge ds-pipeline-table-row__failed-stage">
          실패 단계: {failedStageLabel.split('(')[0].trim()}
        </span>
      </td>
      <td data-label="임베딩 모델"><span className="ds-badge ds-badge--blue">{run.model}</span></td>
      <td className="ds-table-cell--muted" data-label="차원">—</td>
      <td className="ds-table-cell--muted" data-label="청크">—</td>
      <td className="ds-table-cell--muted" data-label="스토리지">—</td>
      <td className="ds-table-cell--time" data-label="경과 시간">{Math.round(run.elapsedSeconds || 0)}초 경과</td>
      <td className="ds-actions-col ds-text-right" data-label="작업">
        <div className="ds-actions-row">
          <Button
            variant="danger"
            size="sm"
            type="button"
            onClick={() => onViewLog?.(run)}
            title="실패 단계 및 모듈 로그 확인"
          >
            <Layers size={12} /> 실패 로그
          </Button>
          {onDelete && (
            <Button
              variant="danger"
              size="sm"
              type="button"
              onClick={() => onDelete(run)}
              disabled={deleting}
              title="실패 작업 기록과 부분 컬렉션 삭제"
            >
              {deleting ? <RefreshCw size={12} className="ds-spin" /> : <Trash2 size={12} />}
              삭제
            </Button>
          )}
        </div>
      </td>
    </tr>
  );
}

interface VectorIndexRowProps {
  readonly compact?: boolean;
  readonly index: VectorIndexInfo;
  readonly editing: boolean;
  readonly editingName: string;
  readonly editError: string;
  readonly saving: boolean;
  readonly deleting: boolean;
  readonly editLocked: boolean;
  readonly onEditingNameChange: (value: string) => void;
  readonly onStartEdit: () => void;
  readonly onCancelEdit: () => void;
  readonly onSave: () => void;
  readonly onPipelineLog?: (index: VectorIndexInfo) => void;
  readonly onSearch: (index: VectorIndexInfo) => void;
  readonly onDetail: (indexId: string) => void;
  readonly onDelete: (indexId: string) => void;
}

export function VectorIndexRow({
  compact = false,
  index,
  editing,
  editingName,
  editError,
  saving,
  deleting,
  editLocked,
  onEditingNameChange,
  onStartEdit,
  onCancelEdit,
  onSave,
  onPipelineLog,
  onSearch,
  onDetail,
  onDelete,
}: VectorIndexRowProps) {
  const companyInputRef = useRef<HTMLInputElement>(null);
  const rowBusy = saving || deleting;
  const companyDisplay = index.company_name || '';
  const companyMessageId = editError
    ? `company-error-${index.index_id}`
    : saving
      ? `company-status-${index.index_id}`
      : undefined;

  useEffect(() => {
    if (editing) companyInputRef.current?.focus();
  }, [editing]);

  if (compact) {
    return (
      <tr
        className={`ds-index-row${saving ? ' ds-index-row--updating' : ''}${deleting ? ' ds-index-row--deleting' : ''}`}
        aria-busy={rowBusy || undefined}
      >
        <td className="ds-mobile-list-cell" colSpan={9}>
          {deleting ? (
            <div className="ds-mobile-list-row ds-mobile-list-row--busy" role="status" aria-live="polite">
              <RefreshCw className="ds-spin" size={13} />
              <strong className="ds-mobile-list-title">{companyDisplay || index.file_name || 'Dataset'}</strong>
              <span className="ds-mobile-list-meta is-danger">삭제 중</span>
            </div>
          ) : editing ? (
            <div className="ds-mobile-company-editor">
              <input
                type="text"
                className="ds-company-inline-input"
                value={editingName}
                onChange={(event) => onEditingNameChange(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') onSave();
                  else if (event.key === 'Escape') onCancelEdit();
                }}
                placeholder="기업명 입력..."
                aria-label="기업명"
                aria-invalid={Boolean(editError)}
                title={editError || undefined}
                disabled={saving}
              />
              <IconButton variant="primary" size="sm" aria-label="기업명 저장" type="button" onClick={onSave} disabled={saving} busy={saving}>
                {saving ? <RefreshCw className="ds-spin" size={12} /> : <Check size={12} />}
              </IconButton>
              <IconButton variant="ghost" size="sm" aria-label="기업명 수정 취소" type="button" onClick={onCancelEdit} disabled={saving}>
                <X size={12} />
              </IconButton>
            </div>
          ) : (
            <div className="ds-mobile-list-row">
              <button
                type="button"
                className="ds-mobile-index-identity"
                title={`${companyDisplay || '기업명 미지정'} · ${index.file_name || 'Dataset'} · 탭하여 기업명 수정`}
                aria-label={`${companyDisplay || '미지정'} 기업명 수정`}
                onClick={onStartEdit}
                disabled={editLocked}
              >
                <Building2 size={14} />
                <strong>{companyDisplay || index.file_name || '+ 기업명 입력'}</strong>
              </button>
              <span className="ds-mobile-list-meta" title="저장된 청크 수">{index.document_count.toLocaleString()}</span>
              <div className="ds-mobile-list-actions">
                {onPipelineLog && (
                  <IconButton variant="ghost" size="sm" aria-label="모듈 로그" type="button" onClick={() => onPipelineLog(index)} disabled={saving}>
                    <Cpu size={13} />
                  </IconButton>
                )}
                <IconButton variant="primary" size="sm" aria-label="검색 테스트" type="button" onClick={() => onSearch(index)} disabled={saving}><Search size={13} /></IconButton>
                <IconButton variant="ghost" size="sm" aria-label="컬렉션 상세" type="button" onClick={() => onDetail(index.index_id)} disabled={saving}><Eye size={13} /></IconButton>
                <IconButton variant="danger" size="sm" aria-label="인덱스 삭제" type="button" onClick={() => onDelete(index.index_id)} disabled={editLocked || saving}><Trash2 size={13} /></IconButton>
              </div>
            </div>
          )}
        </td>
      </tr>
    );
  }

  return (
    <tr
      className={`ds-index-row${saving ? ' ds-index-row--updating' : ''}${deleting ? ' ds-index-row--deleting' : ''}`}
      aria-busy={rowBusy || undefined}
    >
      <td className="ds-font-mono ds-id-cell ds-table__nowrap" data-label="컬렉션 ID">
        <span title={index.index_id}>{index.index_id.slice(0, 10)}...</span>
      </td>
      <td className="ds-table-dataset-name ds-table__nowrap" data-label="대상 데이터셋">{index.file_name || 'Dataset'}</td>
      <td className="ds-table__nowrap" data-label="기업명">
        <div className="ds-company-cell">
          {editing ? (
            <div className="ds-company-editor">
              <div className="ds-company-inline-form">
                <input
                  ref={companyInputRef}
                  type="text"
                  className="ds-company-inline-input"
                  value={editingName}
                  onChange={(event) => onEditingNameChange(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') onSave();
                    else if (event.key === 'Escape') onCancelEdit();
                  }}
                  placeholder="기업명 입력..."
                  aria-label="기업명"
                  aria-invalid={Boolean(editError)}
                  aria-describedby={companyMessageId}
                  disabled={saving}
                />
                <IconButton
                  variant="primary"
                  size="sm"
                  aria-label="기업명 저장"
                  type="button"
                  className="ds-company-inline-save"
                  title="저장 (Enter)"
                  onClick={onSave}
                  disabled={saving}
                  busy={saving}
                >
                  {saving ? <RefreshCw className="ds-spin" size={12} /> : <Check size={12} />}
                </IconButton>
                <IconButton
                  variant="ghost"
                  size="sm"
                  aria-label="기업명 수정 취소"
                  type="button"
                  className="ds-company-inline-cancel"
                  title="취소 (Esc)"
                  onClick={onCancelEdit}
                  disabled={saving}
                >
                  <X size={12} />
                </IconButton>
              </div>
              {editError && (
                <small id={`company-error-${index.index_id}`} className="ds-company-edit-error" role="alert">
                  {editError}
                </small>
              )}
              {saving && (
                <small
                  id={`company-status-${index.index_id}`}
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
                onClick={onStartEdit}
                disabled={editLocked}
              >
                <Building2 size={12} />
                <span>{companyDisplay || '+ 기업명 입력'}</span>
              </button>
              <IconButton
                variant="ghost"
                size="sm"
                aria-label="기업명 수정"
                type="button"
                className="ds-company-edit-btn"
                title="기업명 수정"
                onClick={onStartEdit}
                disabled={editLocked}
              >
                <Edit2 size={12} />
              </IconButton>
            </>
          )}
        </div>
      </td>
      <td className="ds-table__nowrap" data-label="임베딩 모델"><span className="ds-model-badge" title={index.model}>{index.model}</span></td>
      <td className="ds-table__nowrap" data-label="차원"><span className="ds-dim-pill">{index.dimension}D</span></td>
      <td className="ds-table__nowrap" data-label="저장된 청크">
        <div className="ds-chunk-block">
          <div className="ds-chunk-primary"><Layers size={13} /><span>{index.document_count.toLocaleString()}개</span></div>
          {index.duration_seconds !== undefined && index.duration_seconds !== null && (
            <div className="ds-chunk-subtext">
              ⏱️ {index.duration_seconds}s {index.estimated_cost_usd ? `· $${index.estimated_cost_usd.toFixed(4)}` : ''}
            </div>
          )}
        </div>
      </td>
      <td className="ds-table__nowrap" data-label="스토리지">
        <span className="ds-badge ds-badge--green" title="PostgreSQL 16 pgvector HNSW">PostgreSQL + pgvector</span>
      </td>
      <td className="ds-table__nowrap" data-label="생성일시"><span className="ds-time-text"><Clock size={12} /> {formatDate(index.created_at)}</span></td>
      <td className="ds-actions-col ds-text-right ds-table__nowrap" data-label="작업">
        {deleting ? (
          <div className="ds-row-operation ds-row-operation--danger" role="status" aria-live="polite">
            <RefreshCw className="ds-spin" size={13} /><span>데이터 삭제 중...</span>
          </div>
        ) : (
          <div className="ds-actions-row">
            <Button size="sm" type="button" title="4대 모듈 파이프라인 실행 로그 및 세부 단계 확인" onClick={() => onPipelineLog?.(index)} disabled={saving}>
              <Cpu size={13} /><span>모듈 로그</span>
            </Button>
            <Button variant="primary" size="sm" type="button" title="유사도 검색 테스트" onClick={() => onSearch(index)} disabled={saving}>
              <Search size={13} /><span>검색 테스트</span>
            </Button>
            <Button size="sm" type="button" title="청크 및 메타데이터 상세 보기" onClick={() => onDetail(index.index_id)} disabled={saving}>
              <Eye size={13} /><span>상세</span>
            </Button>
            <IconButton variant="danger" size="sm" aria-label="인덱스 삭제" type="button" title="인덱스 삭제" onClick={() => onDelete(index.index_id)} disabled={editLocked || saving}>
              <Trash2 size={13} />
            </IconButton>
          </div>
        )}
      </td>
    </tr>
  );
}
