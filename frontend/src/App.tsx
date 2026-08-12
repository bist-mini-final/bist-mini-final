import { useState } from 'react';
import { X } from 'lucide-react';
import { Header } from './components/Header';
import { PipelineCanvas } from './components/PipelineCanvas';
import { ModulePalette } from './components/Sidebar/ModulePalette';
import { usePipelineController } from './hooks/usePipelineController';
import { usePipelineGraph } from './hooks/usePipelineGraph';
import { useWorkflowPersistence } from './hooks/useWorkflowPersistence';
import { useResizablePanel } from './hooks/useResizablePanel';
import { ModuleExecutionContext } from './contexts/ModuleExecutionContext';

export function App() {
  const [isPaletteOpen, setIsPaletteOpen] = useState(
    () => window.matchMedia('(min-width: 1024px)').matches
  );
  const modulePanel = useResizablePanel();
  const controller = usePipelineController();
  const graph = usePipelineGraph({
    queryText: controller.queryText,
    setQueryText: controller.setQueryText,
    activeStep: controller.activeStep,
    modules: controller.modules,
  });
  const workflow = useWorkflowPersistence(graph, controller.modules.length > 0);
  // Use loose compatibility so that adding new nodes to the canvas does not
  // wipe out the execution results of already-completed nodes.  New nodes have
  // no entry in run.nodes and are therefore shown as idle by applyRun().
  const currentRun = workflow.latestRunCompatibleWithGraph ? workflow.latestRun : null;
  const progressedBatches = currentRun?.batches.filter(
    (batch) => batch.status !== 'pending'
  );
  const activeBatch = progressedBatches
    ? progressedBatches[progressedBatches.length - 1]?.index ?? -1
    : -1;
  const totalBatches = currentRun?.batches.length ?? graph.batchCount;

  const handleAutoRun = async () => {
    if (workflow.isExecuting) {
      workflow.cancelExecution();
      return;
    }
    controller.dismissError();
    try {
      await workflow.executeAll(
        controller.queryText,
        controller.applyWorkflowRun
      );
    } catch (error: unknown) {
      if (!(error instanceof DOMException && error.name === 'AbortError')) {
        controller.reportError(
          error instanceof Error ? error.message : '워크플로 실행에 실패했습니다.'
        );
      }
    }
  };

  const handleNodeExecute = async (nodeId: string) => {
    controller.dismissError();
    graph.clearNodeExecutionState(nodeId);
    graph.resumeNodeExecution(nodeId);
    try {
      await workflow.executeNode(
        nodeId,
        controller.queryText,
        controller.applyWorkflowRun
      );
    } catch (error: unknown) {
      if (!(error instanceof DOMException && error.name === 'AbortError')) {
        controller.reportError(
          error instanceof Error ? error.message : '선택한 모듈 실행에 실패했습니다.'
        );
      }
    }
  };

  const handleClearCache = async () => {
    const confirmed = window.confirm(
      '진행 중인 모듈 실행을 즉시 중단하고 결과 캐시와 모든 실행 이력을 삭제할까요?\n캔버스의 노드와 연결은 유지됩니다.'
    );
    if (!confirmed) return;
    controller.dismissError();
    try {
      await workflow.clearCache();
      controller.clearResults();
    } catch (error: unknown) {
      controller.reportError(
        error instanceof Error ? error.message : '캐시 초기화에 실패했습니다.'
      );
    }
  };

  return (
    <ModuleExecutionContext.Provider
      value={{
        onExecuteNode: (nodeId) => void handleNodeExecute(nodeId),
        onStopExecution: workflow.cancelExecution,
        onClearNodeResult: graph.clearNodeExecutionState,
        isExecuting: workflow.isExecuting,
      }}
    >
      <div className="app-shell">
        <Header
          activeStep={activeBatch}
          totalSteps={totalBatches}
          hasGraphCycle={graph.hasCycle}
          isRunning={workflow.isExecuting}
          hasPipeline={workflow.ready && graph.nodes.length > 0}
          isPaletteOpen={isPaletteOpen}
          onTogglePalette={() => setIsPaletteOpen((open) => !open)}
          onReset={() => {
            controller.reset();
            graph.clearGraph();
          }}
          onToggleRun={() => void handleAutoRun()}
          saveStatus={workflow.saveStatus}
          onSave={() => void workflow.saveNow().catch(() => undefined)}
          isClearingCache={workflow.isClearingCache}
          onClearCache={() => void handleClearCache()}
        />

        {controller.errorMessage && (
          <div className="error-banner" role="alert">
            <span>{controller.errorMessage}</span>
            <button onClick={controller.dismissError} aria-label="오류 메시지 닫기">
              <X className="h-4 w-4" />
            </button>
          </div>
        )}

        <main className="app-workspace">
          <ModulePalette
            modules={controller.modules}
            isOpen={isPaletteOpen}
            onClose={() => setIsPaletteOpen(false)}
            width={modulePanel.width}
            onResizeStart={modulePanel.startResize}
            onResizeBy={modulePanel.resizeBy}
            onAddNode={(type) => {
              graph.addNode(type);
              if (!window.matchMedia('(min-width: 1024px)').matches) {
                setIsPaletteOpen(false);
              }
            }}
          />
          {isPaletteOpen && (
            <button
              className="palette-backdrop"
              onClick={() => setIsPaletteOpen(false)}
              aria-label="모듈 패널 닫기"
            />
          )}
          <PipelineCanvas
            graph={graph}
            modules={controller.modules}
            runs={workflow.runs}
            isPaletteOpen={isPaletteOpen}
            onOpenPalette={() => setIsPaletteOpen(true)}
          />
        </main>
      </div>
    </ModuleExecutionContext.Provider>
  );
}

export default App;
