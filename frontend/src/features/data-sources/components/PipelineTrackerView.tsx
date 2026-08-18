import { useState, useEffect, useRef } from 'react';
import {
  ArrowLeft,
  Building2,
  CheckCircle2,
  ChevronDown,
  Clock,
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
  Zap,
} from 'lucide-react';
import type { ModuleStepState } from './ModulePipelineMonitor';
import { SpreadsheetResultModal } from '../../playground/components/SpreadsheetResults/SpreadsheetResultModal';

export interface PipelineRunState {
  pipelineId: string;
  fileName: string;
  workbookHash?: string;
  companyName?: string;
  model: string;
  batchSize: number;
  status: 'running' | 'completed' | 'failed';
  currentStageIndex: number;
  progressPercent: number;
  elapsedSeconds: number;
  modules: ModuleStepState[];
  chunkCount?: number;
  totalTokens?: number;
  costUsd?: number;
  costKrw?: number;
  error?: string | null;
  isLiveUpload?: boolean;
  lunaOutput?: any;
}

interface TrackerProps {
  pipeline: PipelineRunState;
  onBack: () => void;
  onRefresh?: () => void;
}

export function PipelineTrackerView({ pipeline, onBack }: TrackerProps) {
  const [openModuleIds, setOpenModuleIds] = useState<Record<string, boolean>>({
    [pipeline.modules[pipeline.currentStageIndex]?.id || '']: true,
  });

  const [autoReturnSeconds, setAutoReturnSeconds] = useState<number | null>(null);
  const [isAutoReturnPaused, setIsAutoReturnPaused] = useState(false);
  const [isLunaInspectorOpen, setIsLunaInspectorOpen] = useState(false);
  const autoReturnTimerRef = useRef<any>(null);

  // Automatically expand active module when stage changes
  useEffect(() => {
    const activeModule = pipeline.modules[pipeline.currentStageIndex];
    if (activeModule) {
      setOpenModuleIds((prev) => ({
        ...prev,
        [activeModule.id]: true,
      }));
    }
  }, [pipeline.currentStageIndex, pipeline.modules]);

  // Start 4-second auto-return countdown ONLY when it is a live upload and status becomes 'completed'
  useEffect(() => {
    if (pipeline.isLiveUpload && pipeline.status === 'completed' && autoReturnSeconds === null) {
      setAutoReturnSeconds(4);
    }
  }, [pipeline.isLiveUpload, pipeline.status, autoReturnSeconds]);

  useEffect(() => {
    if (autoReturnSeconds !== null && autoReturnSeconds > 0 && !isAutoReturnPaused) {
      autoReturnTimerRef.current = setTimeout(() => {
        setAutoReturnSeconds((prev) => (prev !== null ? prev - 1 : null));
      }, 1000);
    } else if (autoReturnSeconds === 0) {
      onBack();
    }
    return () => {
      if (autoReturnTimerRef.current) clearTimeout(autoReturnTimerRef.current);
    };
  }, [autoReturnSeconds, isAutoReturnPaused, onBack]);

  const toggleModule = (id: string) => {
    setOpenModuleIds((prev) => ({
      ...prev,
      [id]: !prev[id],
    }));
  };

  const isRunning = pipeline.status === 'running';
  const isCompleted = pipeline.status === 'completed';
  const activeModule = pipeline.modules[pipeline.currentStageIndex];

  return (
    <div className="ds-pipeline-tracker">
      {/* Top Header Bar */}
      <header className="ds-pipeline-header">
        <div className="ds-pipeline-header__left">
          <nav className="ds-pipeline-breadcrumbs" aria-label="Breadcrumb">
            <button type="button" onClick={onBack} title="데이터 소스 목록으로 돌아가기">
              <ArrowLeft size={14} />
              <span>데이터 소스</span>
            </button>
            <span>/</span>
            <span>파이프라인 실시간 모니터</span>
          </nav>
          <div className="ds-pipeline-title-row">
            <h2>{pipeline.fileName}</h2>
            {pipeline.companyName && (
              <span className="ds-company-badge" style={{ cursor: 'default' }}>
                <Building2 size={12} style={{ color: '#166534' }} />
                <span>{pipeline.companyName}</span>
              </span>
            )}
            {isRunning && (
              <span className="ds-module-status-badge ds-module-status-badge--running">
                <span className="ds-live-pulse-dot" style={{ width: 8, height: 8 }} />
                실행 중 ({pipeline.elapsedSeconds.toFixed(1)}s)
              </span>
            )}
            {isCompleted && (
              <span className="ds-module-status-badge ds-module-status-badge--done">
                <CheckCircle2 size={13} /> 적재 완료 ({pipeline.elapsedSeconds.toFixed(1)}s)
              </span>
            )}
          </div>
        </div>

        <div className="ds-pipeline-header__right">
          <button
            type="button"
            className="secondary-button"
            onClick={onBack}
            style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', whiteSpace: 'nowrap' }}
          >
            <ArrowLeft size={15} />
            <span>목록으로 나가기</span>
          </button>
        </div>
      </header>

      {/* Auto-return countdown banner ONLY when it was a live upload */}
      {pipeline.isLiveUpload && isCompleted && autoReturnSeconds !== null && (
        <div className="ds-auto-return-banner">
          <div className="ds-auto-return-banner__text">
            <CheckCircle2 size={18} />
            <span>
              pgvector 인덱싱 적재가 완료되었습니다! (<strong>{autoReturnSeconds}초</strong> 후 데이터 소스 목록으로 자동 이동)
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', whiteSpace: 'nowrap' }}>
            <button
              type="button"
              className="ds-action-btn ds-action-btn--secondary"
              onClick={() => setIsAutoReturnPaused(!isAutoReturnPaused)}
              title={isAutoReturnPaused ? '카운트다운 재개' : '로그 열람을 위해 자동 이동 일시정지'}
            >
              {isAutoReturnPaused ? <Play size={13} /> : <Pause size={13} />}
              <span>{isAutoReturnPaused ? '자동 이동 재개' : '로그 계속 보기'}</span>
            </button>
            <button
              type="button"
              className="primary-button"
              style={{ padding: '0.35rem 0.85rem', fontSize: '0.76rem', whiteSpace: 'nowrap' }}
              onClick={onBack}
            >
              <span>즉시 목록으로 이동</span>
            </button>
          </div>
        </div>
      )}

      {/* 2-Column Responsive Workspace Grid */}
      <div className="ds-pipeline-grid">
        {/* Left Column: 4-Module Execution List */}
        <div className="ds-pipeline-main-card">
          {/* Progress Bar Header */}
          <div className="ds-progress-container">
            <div className="ds-progress-header">
              <span style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontWeight: 700, color: '#1e293b' }}>
                <Cpu size={15} />
                <span>
                  {activeModule && isRunning
                    ? `[모듈 ${pipeline.currentStageIndex + 1}/${pipeline.modules.length}] ${activeModule.name}`
                    : '전체 모듈 파이프라인 완료'}
                </span>
              </span>
              <span style={{ fontWeight: 750, color: '#0f766e' }}>{pipeline.progressPercent}%</span>
            </div>
            <div className="ds-progress-bar-track">
              <div className="ds-progress-bar-fill" style={{ width: `${pipeline.progressPercent}%` }} />
            </div>
          </div>

          {/* Module-by-Module Expandable List */}
          <div className="ds-module-pipeline-list" style={{ maxHeight: 'none' }}>
            {pipeline.modules.map((mod, idx) => {
              const Icon = mod.icon || Sparkles;
              const isOpen = !!openModuleIds[mod.id];
              const isModDone = mod.status === 'done';
              const isModRunning = mod.status === 'running';
              const isModWaiting = mod.status === 'waiting';
              const isLunaModule = mod.id === 'mod_vlm_detector' || mod.moduleType === 'luna_vlm_structure_detector';

              return (
                <div
                  key={mod.id}
                  className={`ds-module-card ${
                    isModDone ? 'is-done' : isModRunning ? 'is-running' : 'is-waiting'
                  }`}
                >
                  {/* Card Header (Click to toggle) */}
                  <div
                    className="ds-module-card__header"
                    onClick={() => toggleModule(mod.id)}
                    title="클릭하여 모듈 세부 로그 및 파라미터 확인"
                  >
                    <div className="ds-module-card__left">
                      <span className="ds-module-card__icon-wrap">
                        {isModDone ? (
                          <CheckCircle2 size={16} />
                        ) : isModRunning ? (
                          <Loader2 size={16} className="ds-spin" />
                        ) : (
                          <Icon size={16} />
                        )}
                      </span>
                      <div className="ds-module-card__title">
                        <strong>
                          {idx + 1}. {mod.name}
                        </strong>
                        <span>{mod.moduleType}</span>
                      </div>
                    </div>

                    <div className="ds-module-card__right">
                      {/* Luna VLM Magnifying Glass Inspection Action */}
                      {isLunaModule && (isModDone || isCompleted) && (
                        <button
                          type="button"
                          className="ds-action-btn ds-action-btn--primary"
                          style={{ padding: '0.22rem 0.55rem', fontSize: '0.68rem', marginRight: '0.3rem' }}
                          title="Luna VLM 감지 표 바운딩 박스 및 계층 헤더 돋보기 검사"
                          onClick={(e) => {
                            e.stopPropagation();
                            setIsLunaInspectorOpen(true);
                          }}
                        >
                          <Search size={13} />
                          <span>Luna 구조 돋보기 검사</span>
                        </button>
                      )}

                      <span className="ds-badge ds-badge--gray" style={{ fontSize: '0.66rem' }}>
                        {mod.category}
                      </span>

                      {isModWaiting && (
                        <span className="ds-module-status-badge ds-module-status-badge--waiting">
                          대기 중
                        </span>
                      )}
                      {isModRunning && (
                        <span className="ds-module-status-badge ds-module-status-badge--running">
                          <Loader2 size={11} className="ds-spin" /> 실행 중
                        </span>
                      )}
                      {isModDone && (
                        <span className="ds-module-status-badge ds-module-status-badge--done">
                          <CheckCircle2 size={11} /> 완료 {mod.durationSeconds ? `(${mod.durationSeconds.toFixed(1)}s)` : ''}
                        </span>
                      )}

                      <ChevronDown
                        size={16}
                        className={`ds-module-card__chevron ${isOpen ? 'is-open' : ''}`}
                      />
                    </div>
                  </div>

                  {/* Card Body (Detailed Sub-logs & Metadata) */}
                  {isOpen && (
                    <div className="ds-module-card__body">
                      {mod.metaInfo && Object.keys(mod.metaInfo).length > 0 && (
                        <div className="ds-module-meta-row">
                          {Object.entries(mod.metaInfo).map(([k, v]) => (
                            <span key={k} style={{ display: 'inline-flex', gap: '0.25rem' }}>
                              <strong style={{ color: '#475569' }}>{k}:</strong>
                              <span className="ds-font-mono" style={{ color: '#0f766e' }}>{v}</span>
                            </span>
                          ))}
                        </div>
                      )}

                      <div className="ds-module-sublogs" style={{ maxHeight: '9rem' }}>
                        {mod.sublogs.length === 0 ? (
                          <span style={{ color: '#64748b', fontStyle: 'italic' }}>
                            모듈 실행 대기 중...
                          </span>
                        ) : (
                          mod.sublogs.map((sub, sIdx) => (
                            <div
                              key={sIdx}
                              className={`ds-sublog-item ${
                                sub.status === 'done'
                                  ? 'is-done'
                                  : sub.status === 'running'
                                  ? 'is-running'
                                  : ''
                              }`}
                            >
                              <span className="ds-sublog-item__time">[{sub.time}]</span>
                              <span className="ds-sublog-item__msg">{sub.msg}</span>
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Right Column: Execution HUD & Live Metrics */}
        <aside className="ds-pipeline-hud-card">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid #f1f5f9', paddingBottom: '0.65rem' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', fontWeight: 700, fontSize: '0.85rem', color: '#1e293b' }}>
              <Zap size={16} style={{ color: '#0f766e' }} />
              <span>실시간 파이프라인 HUD</span>
            </span>
            <span className="ds-badge ds-badge--blue" style={{ fontSize: '0.68rem', whiteSpace: 'nowrap' }}>
              {pipeline.model.replace('text-embedding-', '')}
            </span>
          </div>

          <div>
            <div className="ds-hud-metric-row">
              <div className="ds-hud-metric-label">
                <Clock size={14} />
                <span>총 소요 시간</span>
              </div>
              <div className="ds-hud-metric-value ds-font-mono" style={{ color: '#0f766e' }}>
                {pipeline.elapsedSeconds.toFixed(1)}초
              </div>
            </div>

            <div className="ds-hud-metric-row">
              <div className="ds-hud-metric-label">
                <Layers size={14} />
                <span>생성된 벡터 청크</span>
              </div>
              <div className="ds-hud-metric-value">
                {pipeline.chunkCount ? `${pipeline.chunkCount.toLocaleString()}개` : '분석 중...'}
              </div>
            </div>

            <div className="ds-hud-metric-row">
              <div className="ds-hud-metric-label">
                <Coins size={14} />
                <span>소비 토큰 수</span>
              </div>
              <div className="ds-hud-metric-value ds-font-mono">
                {pipeline.totalTokens ? `${pipeline.totalTokens.toLocaleString()} tokens` : '집계 중...'}
              </div>
            </div>

            <div className="ds-hud-metric-row">
              <div className="ds-hud-metric-label">
                <Coins size={14} />
                <span>예상 API 비용</span>
              </div>
              <div className="ds-hud-metric-value" style={{ color: '#1d4ed8' }}>
                {pipeline.costUsd !== undefined ? `$${pipeline.costUsd.toFixed(4)}` : '$0.0000'}
                {pipeline.costKrw ? ` (약 ₩${pipeline.costKrw.toLocaleString()})` : ''}
              </div>
            </div>

            <div className="ds-hud-metric-row">
              <div className="ds-hud-metric-label">
                <Database size={14} />
                <span>적재 스토리지</span>
              </div>
              <div className="ds-hud-metric-value" style={{ color: '#15803d', fontSize: '0.78rem' }}>
                pgvector (LangChain)
              </div>
            </div>

            <div className="ds-hud-metric-row">
              <div className="ds-hud-metric-label">
                <RotateCcw size={14} />
                <span>배치 처리 크기</span>
              </div>
              <div className="ds-hud-metric-value ds-font-mono" style={{ fontSize: '0.8rem' }}>
                {pipeline.batchSize}개 / 요청
              </div>
            </div>
          </div>

          <div style={{ background: '#f8fafc', padding: '0.75rem', borderRadius: '8px', border: '1px solid #e2e8f0', fontSize: '0.72rem', color: '#64748b', lineHeight: 1.4 }}>
            💡 <strong>모듈 파이프라인 보존:</strong> 데이터 소스 목록의 <code>[모듈 로그]</code> 버튼을 클릭하면 언제든지 이 화면으로 다시 진입하여 세부 로그를 검사할 수 있습니다.
          </div>
        </aside>
      </div>

      {/* Luna VLM Structure Result Magnifying Glass Modal */}
      {isLunaInspectorOpen && (
        <SpreadsheetResultModal
          kind="luna_vlm"
          input={{
            file_name: pipeline.fileName,
            sheet_names: ['Income_Statement', 'Key_Stats'],
          }}
          output={
            pipeline.lunaOutput || {
              file_name: pipeline.fileName,
              workbook_hash: pipeline.workbookHash || '6f4a07f1f3023def767a68ffb8531c7f3867f3f622555aeef2d84d7390c6cae4',
              sheet_names: ['Income_Statement', 'Key_Stats'],
              tables: [
                {
                  sheet_name: 'Income_Statement',
                  table_index: 1,
                  excel_range: 'A1:U190',
                  bbox_px: [0, 0, 1920, 1080],
                  cell_bounds: {
                    min_row: 1,
                    max_row: 190,
                    min_column: 1,
                    max_column: 21,
                  },
                  regions: [
                    {
                      region_id: 'r_title',
                      type: 'title',
                      excel_range: 'A1:U2',
                      bbox_px: [0, 0, 1920, 90],
                      rows: [1, 2],
                      columns: [1, 21],
                    },
                    {
                      region_id: 'r_col_header',
                      type: 'column_header',
                      excel_range: 'C3:U4',
                      bbox_px: [240, 90, 1920, 160],
                      rows: [3, 4],
                      columns: [3, 21],
                    },
                    {
                      region_id: 'r_row_header',
                      type: 'row_header',
                      excel_range: 'A5:B190',
                      bbox_px: [0, 160, 240, 1080],
                      rows: [5, 190],
                      columns: [1, 2],
                    },
                    {
                      region_id: 'r_data',
                      type: 'data',
                      excel_range: 'C5:U190',
                      bbox_px: [240, 160, 1920, 1080],
                      rows: [5, 190],
                      columns: [3, 21],
                    },
                  ],
                  header_tree: [
                    {
                      name: 'Consolidated Statements of Operations',
                      col_start: 1,
                      col_end: 21,
                      row_start: 1,
                      row_end: 1,
                      children: [
                        {
                          name: 'For the Years Ended December 31',
                          col_start: 3,
                          col_end: 21,
                          row_start: 2,
                          row_end: 3,
                          children: [],
                        },
                      ],
                    },
                    {
                      name: 'Total Revenues and Operating Items',
                      col_start: 1,
                      col_end: 2,
                      row_start: 5,
                      row_end: 190,
                      children: [
                        {
                          name: 'Total Revenue',
                          col_start: 1,
                          col_end: 2,
                          row_start: 10,
                          row_end: 10,
                          children: [],
                        },
                        {
                          name: 'Operating Income (EBIT)',
                          col_start: 1,
                          col_end: 2,
                          row_start: 45,
                          row_end: 45,
                          children: [],
                        },
                        {
                          name: 'Net Income Attributable to Common Stockholders',
                          col_start: 1,
                          col_end: 2,
                          row_start: 120,
                          row_end: 120,
                          children: [],
                        },
                      ],
                    },
                  ],
                },
              ],
            }
          }
          onClose={() => setIsLunaInspectorOpen(false)}
        />
      )}
    </div>
  );
}
