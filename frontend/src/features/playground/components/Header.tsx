import {
  ChevronDown,
  Clock,
  Coins,
  DatabaseZap,
  FileSpreadsheet,
  PanelLeft,
  PanelLeftClose,
  Play,
  Plus,
  RotateCcw,
  Save,
  Sparkles,
  Square,
} from 'lucide-react';
import { Button, IconButton } from '../../../shared/ui';
import type { SaveStatus } from '../types';

interface ExecutionMetrics {
  totalElapsedMs: number;
  totalCostUsd: number;
  totalTokens: number;
  hasExecution: boolean;
}

export interface WorkflowOption {
  id: string;
  name: string;
  kind: 'standard' | 'user';
  editable: boolean;
  template: boolean;
  nodeCount: number;
  edgeCount: number;
  moduleTypes: string[];
}

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
  metrics?: ExecutionMetrics;
  // Workflow selector
  workflows: WorkflowOption[];
  activeWorkflowId: string;
  onSelectWorkflow: (id: string) => void;
  onOpenWorkflowCreator: () => void;
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
  metrics,
  workflows,
  activeWorkflowId,
  onSelectWorkflow,
  onOpenWorkflowCreator,
}: HeaderProps) {

  return (
    <header className="app-header" data-palette-open={isPaletteOpen}>
      <div className="app-header__brand-card">
        <IconButton
          className="app-header__palette-button"
          variant="ghost"
          size="sm"
          onClick={onTogglePalette}
          aria-label={isPaletteOpen ? '모듈 패널 닫기' : '모듈 패널 열기'}
          aria-expanded={isPaletteOpen}
          title={isPaletteOpen ? '모듈 패널 접기' : '모듈 패널 펼치기'}
        >
          {isPaletteOpen ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeft className="h-4 w-4" />}
        </IconButton>

        <div className="app-header__brand-divider" aria-hidden="true" />

        <div className="brand-mark" aria-label="Excel RAG Flow" title="Excel RAG Flow Visualizer">
          <FileSpreadsheet className="h-4 w-4" />
        </div>

        {workflows.length > 0 && (
          <>
            <div className="app-header__brand-divider" aria-hidden="true" />
            <div className="workflow-selector">
              <select
                className="workflow-selector__select"
                value={activeWorkflowId}
                onChange={(e) => onSelectWorkflow(e.target.value)}
                title="워크플로 전환"
                aria-label="활성 워크플로 선택"
              >
                {workflows.map((wf) => (
                  <option key={wf.id} value={wf.id}>
                    {wf.name} · {wf.editable ? '사용자' : '읽기 전용'}
                  </option>
                ))}
              </select>
              <ChevronDown className="workflow-selector__chevron h-3 w-3" aria-hidden="true" />
            </div>
            <Button
              size="sm"
              onClick={onOpenWorkflowCreator}
              title="편집 가능한 새 워크플로 만들기"
            >
              <Plus className="h-3.5 w-3.5" />
              <span>새 워크플로</span>
            </Button>
          </>
        )}
      </div>

      <div className="app-header__actions">
        {metrics && (metrics.hasExecution || isRunning) && (
          <div className="execution-stats-panel" title="전체 파이프라인 총 실행 통계 (소요 시간 · 비용 · 토큰 수)">
            <div className="execution-stat-item" title="총 소요 시간">
              <Clock className="h-3.5 w-3.5 text-emerald-600" />
              <span>{(metrics.totalElapsedMs / 1000).toFixed(1)}s</span>
            </div>
            <div className="execution-stat-divider" />
            <div className="execution-stat-item" title="총 예상 비용 ($)">
              <Coins className="h-3.5 w-3.5 text-amber-500" />
              <span>${metrics.totalCostUsd < 0.0001 && metrics.totalCostUsd > 0 ? '<0.0001' : metrics.totalCostUsd.toFixed(4)}</span>
            </div>
            <div className="execution-stat-divider" />
            <div className="execution-stat-item" title="총 사용 토큰 수">
              <Sparkles className="h-3.5 w-3.5 text-blue-500" />
              <span>{metrics.totalTokens.toLocaleString()} tk</span>
            </div>
          </div>
        )}

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

        <Button
          variant="danger"
          onClick={onClearCache}
          disabled={isClearingCache}
          title={isRunning ? '현재 실행을 중단하고 캐시와 실행 이력 초기화' : '모듈 결과 캐시와 실행 이력 초기화'}
        >
          <DatabaseZap className={`h-3.5 w-3.5 ${isClearingCache ? 'animate-pulse' : ''}`} />
          <span>{isClearingCache ? '초기화 중' : '캐시 초기화'}</span>
        </Button>

        <Button onClick={onReset} title="파이프라인 초기화">
          <RotateCcw className="h-3.5 w-3.5" />
          <span>초기화</span>
        </Button>
        <Button
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
        </Button>
        <Button
          variant={isRunning ? 'danger-solid' : 'primary'}
          onClick={onToggleRun}
          disabled={!hasPipeline || hasGraphCycle}
          title={isRunning ? '배치 실행 중단' : 'DAG 배치 자동 실행'}
        >
          {isRunning ? <Square className="h-3.5 w-3.5 fill-current" /> : <Play className="h-3.5 w-3.5 fill-current" />}
          <span>{isRunning ? '중단' : '자동 실행'}</span>
        </Button>
      </div>
    </header>
  );
}
