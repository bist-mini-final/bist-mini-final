import { useState, useEffect } from 'react';
import {
  CheckCircle2,
  ChevronDown,
  Clock,
  Loader2,
  Sparkles,
} from 'lucide-react';

export interface ModuleStepState {
  id: string;
  name: string;
  moduleType: string;
  category: string;
  icon: typeof Sparkles;
  status: 'waiting' | 'running' | 'done';
  durationSeconds?: number;
  sublogs: Array<{ time: string; msg: string; status?: 'info' | 'running' | 'done' }>;
  metaInfo?: Record<string, string | number>;
}

interface PipelineMonitorProps {
  fileName: string;
  model: string;
  batchSize: number;
  elapsedSeconds: number;
  currentStageIndex: number; // 0, 1, 2, 3
  progressPercent: number;
  modules: ModuleStepState[];
}

export function ModulePipelineMonitor({
  fileName,
  model,
  batchSize,
  elapsedSeconds,
  currentStageIndex,
  progressPercent,
  modules,
}: PipelineMonitorProps) {
  // Track open/collapsed state of each module card
  const [openModuleIds, setOpenModuleIds] = useState<Record<string, boolean>>({
    [modules[0]?.id || '']: true,
  });

  // Automatically expand active module when stage changes
  useEffect(() => {
    const activeModule = modules[currentStageIndex];
    if (activeModule) {
      setOpenModuleIds((prev) => ({
        ...prev,
        [activeModule.id]: true,
      }));
    }
  }, [currentStageIndex, modules]);

  const toggleModule = (id: string) => {
    setOpenModuleIds((prev) => ({
      ...prev,
      [id]: !prev[id],
    }));
  };

  const activeModule = modules[currentStageIndex];

  return (
    <div className="ds-live-monitor">
      {/* Top Header Status & Live Elapsed Timer */}
      <div className="ds-live-monitor__header">
        <div className="ds-live-monitor__status">
          <span className="ds-live-pulse-dot" />
          <div>
            <strong style={{ fontSize: '0.88rem', color: '#0f172a' }}>
              {activeModule
                ? `⚡ [모듈 ${currentStageIndex + 1}/${modules.length}] ${activeModule.name} 실행 중...`
                : '모듈 파이프라인 완료'}
            </strong>
            <small style={{ display: 'block', color: '#64748b', fontSize: '0.72rem' }}>
              대상: {fileName} · {model} · 배치 {batchSize}
            </small>
          </div>
        </div>
        <div className="ds-live-monitor__timer">
          <Clock size={14} />
          <span>{elapsedSeconds.toFixed(1)}s</span>
        </div>
      </div>

      {/* Progress bar */}
      <div className="ds-progress-container">
        <div className="ds-progress-header">
          <span>파이프라인 전체 진행률</span>
          <span style={{ fontWeight: 750, color: '#0f766e' }}>{progressPercent}%</span>
        </div>
        <div className="ds-progress-bar-track">
          <div className="ds-progress-bar-fill" style={{ width: `${progressPercent}%` }} />
        </div>
      </div>

      {/* Module-Centric Interactive List */}
      <div className="ds-module-pipeline-list">
        {modules.map((mod, idx) => {
          const Icon = mod.icon;
          const isOpen = !!openModuleIds[mod.id];
          const isDone = mod.status === 'done';
          const isRunning = mod.status === 'running';
          const isWaiting = mod.status === 'waiting';

          return (
            <div
              key={mod.id}
              className={`ds-module-card ${
                isDone ? 'is-done' : isRunning ? 'is-running' : 'is-waiting'
              }`}
            >
              {/* Card Header (Clickable) */}
              <div
                className="ds-module-card__header"
                onClick={() => toggleModule(mod.id)}
                title="클릭하여 모듈 세부 로그 및 입출력 확인"
              >
                <div className="ds-module-card__left">
                  <span className="ds-module-card__icon-wrap">
                    {isDone ? (
                      <CheckCircle2 size={16} />
                    ) : isRunning ? (
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
                  <span className="ds-badge ds-badge--gray" style={{ fontSize: '0.66rem' }}>
                    {mod.category}
                  </span>

                  {isWaiting && (
                    <span className="ds-module-status-badge ds-module-status-badge--waiting">
                      대기 중
                    </span>
                  )}
                  {isRunning && (
                    <span className="ds-module-status-badge ds-module-status-badge--running">
                      <Loader2 size={11} className="ds-spin" /> 실행 중 ({elapsedSeconds.toFixed(1)}s)
                    </span>
                  )}
                  {isDone && (
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
                  {/* Metadata key-value pills if present */}
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

                  {/* Inner Detailed Terminal Sub-logs */}
                  <div className="ds-module-sublogs">
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
  );
}
