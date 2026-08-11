import {
  CheckCircle2,
  DatabaseZap,
  FileSpreadsheet,
  PanelLeft,
  Play,
  RotateCcw,
  Save,
  Square,
  X,
} from 'lucide-react';
import type { SaveStatus } from '../types';

interface HeaderProps {
  activeStep: number;
  totalSteps: number;
  hasGraphCycle: boolean;
  isRunning: boolean;
  hasPipeline: boolean;
  isPaletteOpen: boolean;
  onTogglePalette: () => void;
  onReset: () => void;
  onToggleRun: () => void;
  saveStatus: SaveStatus;
  onSave: () => void;
  isClearingCache: boolean;
  onClearCache: () => void;
}

export function Header({
  activeStep,
  totalSteps,
  hasGraphCycle,
  isRunning,
  hasPipeline,
  isPaletteOpen,
  onTogglePalette,
  onReset,
  onToggleRun,
  saveStatus,
  onSave,
  isClearingCache,
  onClearCache,
}: HeaderProps) {
  return (
    <header className="app-header">
      <div className="app-header__brand-row">
        <button
          className="icon-button app-header__palette-button"
          onClick={onTogglePalette}
          aria-label={isPaletteOpen ? '모듈 패널 닫기' : '모듈 패널 열기'}
          aria-expanded={isPaletteOpen}
        >
          {isPaletteOpen ? <X className="h-4 w-4" /> : <PanelLeft className="h-4 w-4" />}
        </button>

        <div className="brand-mark" aria-hidden="true">
          <FileSpreadsheet className="h-5 w-5" />
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="truncate text-sm font-bold tracking-tight text-slate-950">
              Excel RAG Flow
            </h1>
            <span className="brand-badge">
              <CheckCircle2 className="h-3 w-3" /> DAG Runner
            </span>
          </div>
          <p className="app-header__subtitle">질문 입력 · 모듈 조합 · 결과 확인</p>
        </div>
      </div>

      <div className="app-header__actions">
        {hasPipeline && (
          <div
            className="step-progress"
            data-invalid={hasGraphCycle}
            aria-label={hasGraphCycle ? '순환 연결 감지' : `DAG ${activeStep + 1}번째 배치`}
          >
            <span>
              {hasGraphCycle
                ? '순환 연결 확인'
                : `Batch ${Math.max(0, activeStep + 1)} / ${totalSteps}`}
            </span>
            {!hasGraphCycle && (
              <div className="step-progress__dots" aria-hidden="true">
                {Array.from({ length: totalSteps }).map((_, index) => (
                  <i
                    key={index}
                    data-state={index < activeStep ? 'done' : index === activeStep ? 'active' : 'idle'}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        <button
          className="control-button control-button--danger"
          onClick={onClearCache}
          disabled={isClearingCache}
          title={isRunning ? '현재 실행을 중단하고 캐시와 실행 이력 초기화' : '모듈 결과 캐시와 실행 이력 초기화'}
        >
          <DatabaseZap className={`h-3.5 w-3.5 ${isClearingCache ? 'animate-pulse' : ''}`} />
          <span>{isClearingCache ? '초기화 중' : '캐시 초기화'}</span>
        </button>

        <button className="control-button" onClick={onReset} title="파이프라인 초기화">
          <RotateCcw className="h-3.5 w-3.5" />
          <span>초기화</span>
        </button>
        <button
          className="control-button"
          onClick={onSave}
          disabled={saveStatus === 'loading' || saveStatus === 'saving'}
          title="현재 캔버스를 JSON 파일로 저장"
        >
          <Save className="h-3.5 w-3.5" />
          <span>
            {saveStatus === 'loading'
              ? '불러오는 중'
              : saveStatus === 'saving'
              ? '저장 중'
              : saveStatus === 'error'
                ? '저장 재시도'
                : '저장됨'}
          </span>
        </button>
        <button
          className={`control-button control-button--primary ${isRunning ? 'is-running' : ''}`}
          onClick={onToggleRun}
          disabled={!hasPipeline || hasGraphCycle}
          title={isRunning ? '배치 실행 중단' : 'DAG 배치 자동 실행'}
        >
          {isRunning ? <Square className="h-3.5 w-3.5 fill-current" /> : <Play className="h-3.5 w-3.5 fill-current" />}
          <span>{isRunning ? '중단' : '자동 실행'}</span>
        </button>
      </div>
    </header>
  );
}
