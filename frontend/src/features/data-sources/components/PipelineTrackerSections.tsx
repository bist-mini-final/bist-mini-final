import {
  AlertCircle,
  ArrowLeft,
  Building2,
  CheckCircle2,
  ChevronDown,
  Clock,
  CloudCog,
  Coins,
  Cpu,
  Database,
  Layers,
  Loader2,
  Pause,
  Play,
  RotateCcw,
  Search,
  Sparkles,
  Square,
  Trash2,
  Zap,
} from 'lucide-react';
import type { ReactNode } from 'react';
import { Button } from '../../../shared/ui';
import type { ModuleStepState, PipelineRunState } from '../pipelineTypes';

interface PipelineTrackerHeaderProps {
  readonly pipeline: PipelineRunState;
  readonly isCancelling: boolean;
  readonly isDeleting: boolean;
  readonly onBack: () => void;
  readonly onCancel?: () => void;
  readonly onDelete?: () => void;
}

export function PipelineTrackerHeader({
  pipeline,
  isCancelling,
  isDeleting,
  onBack,
  onCancel,
  onDelete,
}: PipelineTrackerHeaderProps) {
  const isRunning = pipeline.status === 'running';
  const isQueued = pipeline.status === 'queued';
  const isPaused = pipeline.status === 'paused';
  const isCompleted = pipeline.status === 'completed';
  const isFailed = pipeline.status === 'failed';

  return (
    <header className="ds-pipeline-header">
      <div className="ds-pipeline-header__left">
        <nav className="ds-pipeline-breadcrumbs" aria-label="Breadcrumb">
          <button type="button" onClick={onBack} title="데이터 소스 목록으로 돌아가기">
            <ArrowLeft size={14} /><span>데이터 소스</span>
          </button>
          <span>/</span><span>파이프라인 실시간 모니터</span>
        </nav>
        <div className="ds-pipeline-title-row">
          <h2>{pipeline.fileName}</h2>
          {pipeline.scheduler?.backend === 'kubernetes' && (
            <span className="ds-badge ds-badge--blue ds-scheduler-badge">
              <CloudCog size={12} />Kubernetes Job
              <span className={pipeline.scheduler.workerActive ? 'is-active' : 'is-idle'}>
                {pipeline.scheduler.workerActive ? '작업 할당됨' : isQueued ? 'KEDA 큐 대기' : '작업 종료'}
              </span>
            </span>
          )}
          {pipeline.companyName && (
            <span className="ds-company-badge ds-company-badge--static">
              <Building2 size={12} /><span>{pipeline.companyName}</span>
            </span>
          )}
          {isRunning && (
            <span className="ds-module-status-badge ds-module-status-badge--running">
              <span className="ds-live-pulse-dot" />실행 중 ({pipeline.elapsedSeconds.toFixed(1)}s)
            </span>
          )}
          {isQueued && (
            <span className="ds-module-status-badge ds-module-status-badge--waiting">
              <Clock size={13} /> KEDA 배치 큐 대기 중
            </span>
          )}
          {isCompleted && (
            <span className="ds-module-status-badge ds-module-status-badge--done">
              <CheckCircle2 size={13} /> 적재 완료 ({pipeline.elapsedSeconds.toFixed(1)}s)
            </span>
          )}
          {isPaused && (
            <span className="ds-module-status-badge ds-module-status-badge--paused">
              <Pause size={13} /> 사용자 중단
            </span>
          )}
          {isFailed && (
            <span className="ds-module-status-badge ds-module-status-badge--failed">
              <AlertCircle size={13} /> 실행 실패
            </span>
          )}
        </div>
      </div>

      <div className="ds-pipeline-header__right">
        {(isRunning || isQueued) && onCancel && (
          <Button
            variant="danger"
            type="button"
            onClick={onCancel}
            disabled={isCancelling}
            title="현재 모듈 실행을 중단하고 나중에 같은 지점부터 재개"
          >
            {isCancelling ? <Loader2 size={14} className="ds-spin" /> : <Square size={13} />}
            <span>{isCancelling ? '중단 중...' : '작업 중단'}</span>
          </Button>
        )}
        {!isCompleted && onDelete && (
          <Button
            variant="danger"
            type="button"
            onClick={onDelete}
            disabled={isDeleting || isCancelling}
            title="실행 기록과 생성 중인 부분 컬렉션 삭제 (원본 Excel은 보존)"
          >
            {isDeleting ? <Loader2 size={14} className="ds-spin" /> : <Trash2 size={14} />}
            <span>{isDeleting ? '삭제 중...' : '작업 삭제'}</span>
          </Button>
        )}
        <Button type="button" onClick={onBack} className="ds-nowrap-action">
          <ArrowLeft size={15} /><span>목록으로 나가기</span>
        </Button>
      </div>
    </header>
  );
}

interface PipelineStateNoticeProps {
  readonly pipeline: PipelineRunState;
  readonly onResume?: () => void;
}

export function PipelineStateNotice({ pipeline, onResume }: PipelineStateNoticeProps) {
  if (pipeline.status === 'failed') {
    return (
      <div className="ds-error-alert ds-pipeline-notice">
        <AlertCircle size={16} />
        <span>{pipeline.error || '워크플로 모듈 실행 중 오류가 발생했습니다.'}</span>
        {onResume && (
          <Button type="button" onClick={onResume}>
            <RotateCcw size={13} /> 실패 모듈부터 다시 실행
          </Button>
        )}
      </div>
    );
  }

  if (pipeline.status === 'paused') {
    return (
      <div className="ds-paused-alert ds-pipeline-notice">
        <Pause size={16} />
        <span>사용자 요청으로 작업이 중단됐습니다. 완료된 모듈 결과는 보존됩니다.</span>
        {onResume && (
          <Button type="button" onClick={onResume}>
            <RotateCcw size={13} /> 중단 지점부터 다시 실행
          </Button>
        )}
      </div>
    );
  }

  return null;
}

interface AutoReturnBannerProps {
  readonly seconds: number;
  readonly paused: boolean;
  readonly onTogglePaused: () => void;
  readonly onBack: () => void;
}

export function AutoReturnBanner({
  seconds,
  paused,
  onTogglePaused,
  onBack,
}: AutoReturnBannerProps) {
  return (
    <div className="ds-auto-return-banner">
      <div className="ds-auto-return-banner__text">
        <CheckCircle2 size={18} />
        <span>pgvector 인덱싱 적재가 완료되었습니다! (<strong>{seconds}초</strong> 후 데이터 소스 목록으로 자동 이동)</span>
      </div>
      <div className="ds-auto-return-banner__actions">
        <Button
          size="sm"
          type="button"
          onClick={onTogglePaused}
          title={paused ? '카운트다운 재개' : '로그 열람을 위해 자동 이동 일시정지'}
        >
          {paused ? <Play size={13} /> : <Pause size={13} />}
          <span>{paused ? '자동 이동 재개' : '로그 계속 보기'}</span>
        </Button>
        <Button variant="primary" size="sm" type="button" onClick={onBack}>즉시 목록으로 이동</Button>
      </div>
    </div>
  );
}

interface VisibleProgress {
  readonly label: string;
  readonly completed: number;
  readonly total: number;
  readonly unit: string;
  readonly percent: number;
  readonly completedItems?: number;
  readonly totalItems?: number;
  readonly currentItem?: string;
}

function visibleProgressFor(module: ModuleStepState): VisibleProgress | undefined {
  if (module.liveProgress) return module.liveProgress;
  if (!module.batchProgress) return undefined;
  return {
    label: '배치 처리',
    completed: module.batchProgress.completed,
    total: module.batchProgress.total,
    unit: '배치',
    percent: Math.min(
      100,
      (module.batchProgress.completed / Math.max(1, module.batchProgress.total)) * 100,
    ),
    completedItems: module.batchProgress.completedItems,
    totalItems: module.batchProgress.totalItems,
  };
}

interface PipelineModuleListProps {
  readonly pipeline: PipelineRunState;
  readonly openModuleIds: Readonly<Record<string, boolean>>;
  readonly onToggleModule: (id: string) => void;
  readonly onInspectLuna: () => void;
}

export function PipelineModuleList({
  pipeline,
  openModuleIds,
  onToggleModule,
  onInspectLuna,
}: PipelineModuleListProps) {
  const activeModule = pipeline.modules[pipeline.currentStageIndex];
  const isRunning = pipeline.status === 'running';
  const isQueued = pipeline.status === 'queued';
  const isFailed = pipeline.status === 'failed';
  const isCompleted = pipeline.status === 'completed';

  return (
    <div className="ds-pipeline-main-card">
      <div className="ds-progress-container">
        <div className="ds-progress-header">
          <span className="ds-progress-header__title">
            <Cpu size={15} />
            <span>
              {activeModule && isRunning
                ? `[모듈 ${pipeline.currentStageIndex + 1}/${pipeline.modules.length}] ${activeModule.name}`
                : isQueued
                  ? '서버 작업 큐에서 실행 대기 중'
                  : isFailed
                    ? `모듈 ${pipeline.currentStageIndex + 1}에서 실행 실패`
                    : '전체 모듈 파이프라인 완료'}
            </span>
          </span>
          <span className="ds-progress-header__value">{pipeline.progressPercent}%</span>
        </div>
        <div className="ds-progress-bar-track">
          <div className="ds-progress-bar-fill" style={{ width: `${pipeline.progressPercent}%` }} />
        </div>
      </div>

      <div className="ds-module-pipeline-list ds-module-pipeline-list--expanded">
        {pipeline.modules.map((module, index) => {
          const Icon = module.icon || Sparkles;
          const isOpen = Boolean(openModuleIds[module.id]);
          const isDone = module.status === 'done';
          const isModuleRunning = module.status === 'running';
          const isWaiting = module.status === 'waiting';
          const isModuleFailed = module.status === 'failed';
          const isLunaModule = module.id === 'mod_vlm_detector'
            || module.moduleType === 'luna_vlm_structure_detector';
          const visibleProgress = visibleProgressFor(module);

          return (
            <div
              key={module.id}
              className={`ds-module-card ${isDone
                ? 'is-done'
                : isModuleRunning
                  ? 'is-running'
                  : isModuleFailed
                    ? 'is-failed'
                    : 'is-waiting'}`}
            >
              <div
                className="ds-module-card__header"
                role="button"
                tabIndex={0}
                aria-expanded={isOpen}
                onClick={() => onToggleModule(module.id)}
                onKeyDown={(event) => {
                  if ((event.target as HTMLElement).closest('.ui-button')) return;
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    onToggleModule(module.id);
                  }
                }}
                title="클릭하여 모듈 세부 로그 및 파라미터 확인"
              >
                <div className="ds-module-card__left">
                  <span className="ds-module-card__icon-wrap">
                    {isDone
                      ? <CheckCircle2 size={16} />
                      : isModuleRunning
                        ? <Loader2 size={16} className="ds-spin" />
                        : isModuleFailed
                          ? <AlertCircle size={16} />
                          : <Icon size={16} />}
                  </span>
                  <div className="ds-module-card__title">
                    <strong>{index + 1}. {module.name}</strong><span>{module.moduleType}</span>
                  </div>
                </div>

                <div className="ds-module-card__right">
                  {isLunaModule && (isDone || isCompleted) && pipeline.lunaOutput && (
                    <Button
                      variant="primary"
                      size="sm"
                      type="button"
                      className="ds-luna-inspect-action"
                      title="Luna VLM 감지 표 바운딩 박스 및 계층 헤더 돋보기 검사"
                      onClick={(event) => {
                        event.stopPropagation();
                        onInspectLuna();
                      }}
                    >
                      <Search size={13} /><span>Luna 구조 돋보기 검사</span>
                    </Button>
                  )}
                  <span className="ds-badge ds-badge--gray ds-module-category-badge">{module.category}</span>
                  {isWaiting && <span className="ds-module-status-badge ds-module-status-badge--waiting">대기 중</span>}
                  {isModuleRunning && (
                    <span className="ds-module-status-badge ds-module-status-badge--running">
                      <Loader2 size={11} className="ds-spin" /> 실행 중
                      {visibleProgress ? ` ${Math.round(visibleProgress.percent)}%` : ''}
                    </span>
                  )}
                  {isDone && (
                    <span className="ds-module-status-badge ds-module-status-badge--done">
                      <CheckCircle2 size={11} /> 완료 {module.durationSeconds ? `(${module.durationSeconds.toFixed(1)}s)` : ''}
                    </span>
                  )}
                  {isModuleFailed && (
                    <span className="ds-module-status-badge ds-module-status-badge--failed">
                      <AlertCircle size={11} /> 실패
                    </span>
                  )}
                  <ChevronDown size={16} className={`ds-module-card__chevron ${isOpen ? 'is-open' : ''}`} />
                </div>
              </div>

              {isOpen && (
                <div className="ds-module-card__body">
                  {visibleProgress && (
                    <div className="ds-batch-progress" aria-label={`${module.name} 진행률`}>
                      <div className="ds-batch-progress__label">
                        <strong>
                          {visibleProgress.unit === '배치'
                            ? `${visibleProgress.completed}/${visibleProgress.total} 배치 완료`
                            : `${visibleProgress.label} ${visibleProgress.completed}/${visibleProgress.total} ${visibleProgress.unit}`}
                        </strong>
                        {visibleProgress.totalItems !== undefined && (
                          <span>문서 {(visibleProgress.completedItems ?? 0).toLocaleString()}/{visibleProgress.totalItems.toLocaleString()}개</span>
                        )}
                        {visibleProgress.currentItem && <span>현재: {visibleProgress.currentItem}</span>}
                      </div>
                      <div className="ds-batch-progress__track">
                        <div
                          className="ds-batch-progress__fill"
                          role="progressbar"
                          aria-valuemin={0}
                          aria-valuemax={visibleProgress.total}
                          aria-valuenow={visibleProgress.completed}
                          aria-label={`${module.name} 완료 ${visibleProgress.unit} 수`}
                          style={{ width: `${visibleProgress.percent}%` }}
                        />
                      </div>
                    </div>
                  )}
                  {module.metaInfo && Object.keys(module.metaInfo).length > 0 && (
                    <div className="ds-module-meta-row">
                      {Object.entries(module.metaInfo).map(([key, value]) => (
                        <span key={key} className="ds-module-meta-item">
                          <strong>{key}:</strong><span className="ds-font-mono">{value}</span>
                        </span>
                      ))}
                    </div>
                  )}
                  <div className="ds-module-sublogs ds-module-sublogs--tracker">
                    {module.sublogs.length === 0 ? (
                      <span className="ds-module-sublogs__empty">모듈 실행 대기 중...</span>
                    ) : module.sublogs.map((sublog, sublogIndex) => (
                      <div
                        key={`${sublog.time}-${sublogIndex}`}
                        className={`ds-sublog-item ${sublog.status === 'done'
                          ? 'is-done'
                          : sublog.status === 'running'
                            ? 'is-running'
                            : sublog.status === 'failed'
                              ? 'is-failed'
                              : ''}`}
                      >
                        <span className="ds-sublog-item__time">[{sublog.time}]</span>
                        <span className="ds-sublog-item__msg">{sublog.msg}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

interface PipelineHudProps {
  readonly pipeline: PipelineRunState;
}

export function PipelineHud({ pipeline }: PipelineHudProps) {
  const isQueued = pipeline.status === 'queued';

  return (
    <aside className="ds-pipeline-hud-card">
      <div className="ds-pipeline-hud-card__header">
        <span className="ds-pipeline-hud-card__title"><Zap size={16} /><span>실시간 파이프라인 HUD</span></span>
        <span className="ds-badge ds-badge--blue ds-pipeline-hud-card__model">
          {pipeline.model.replace('text-embedding-', '')}
        </span>
      </div>
      <div>
        <HudMetric icon={<CloudCog size={14} />} label="배치 실행 상태">
          <div className="ds-hud-metric-value ds-scheduler-value">
            {pipeline.scheduler?.backend === 'kubernetes'
              ? pipeline.scheduler.workerActive
                ? 'Kubernetes Job 실행 중'
                : isQueued
                  ? 'KEDA 스케일링 대기'
                  : 'Kubernetes Job 종료'
              : '대화형 실행'}
            {pipeline.scheduler?.externalRunId && (
              <small title={pipeline.scheduler.externalRunId}>{pipeline.scheduler.externalRunId.slice(0, 18)}</small>
            )}
          </div>
        </HudMetric>
        <HudMetric icon={<Clock size={14} />} label="총 소요 시간">
          <div className="ds-hud-metric-value ds-hud-metric-value--accent ds-font-mono">{pipeline.elapsedSeconds.toFixed(1)}초</div>
        </HudMetric>
        <HudMetric icon={<Layers size={14} />} label="생성된 벡터 청크">
          <div className="ds-hud-metric-value">{pipeline.chunkCount != null ? `${pipeline.chunkCount.toLocaleString()}개` : '분석 중...'}</div>
        </HudMetric>
        <HudMetric icon={<Coins size={14} />} label="소비 토큰 수">
          <div className="ds-hud-metric-value ds-font-mono">{pipeline.totalTokens != null ? `${pipeline.totalTokens.toLocaleString()} tokens` : '집계 중...'}</div>
        </HudMetric>
        <HudMetric icon={<Coins size={14} />} label="예상 API 비용">
          <div className="ds-hud-metric-value ds-hud-metric-value--info">
            {pipeline.costUsd != null ? `$${pipeline.costUsd.toFixed(4)}` : '$0.0000'}
            {pipeline.costKrw != null ? ` (약 ₩${pipeline.costKrw.toLocaleString()})` : ''}
          </div>
        </HudMetric>
        <HudMetric icon={<Database size={14} />} label="적재 스토리지">
          <div className="ds-hud-metric-value ds-hud-metric-value--storage">PostgreSQL + pgvector</div>
        </HudMetric>
        <HudMetric icon={<RotateCcw size={14} />} label="배치 처리 크기">
          <div className="ds-hud-metric-value ds-hud-metric-value--compact ds-font-mono">{pipeline.batchSize}개 / 요청</div>
        </HudMetric>
      </div>
      <div className="ds-pipeline-hud-card__note">
        💡 <strong>모듈 파이프라인 보존:</strong> 데이터 소스 목록의 <code>[모듈 로그]</code> 버튼을 클릭하면 언제든지 이 화면으로 다시 진입하여 세부 로그를 검사할 수 있습니다.
      </div>
    </aside>
  );
}

function HudMetric({
  icon,
  label,
  children,
}: {
  readonly icon: ReactNode;
  readonly label: string;
  readonly children: ReactNode;
}) {
  return (
    <div className="ds-hud-metric-row">
      <div className="ds-hud-metric-label">{icon}<span>{label}</span></div>
      {children}
    </div>
  );
}
