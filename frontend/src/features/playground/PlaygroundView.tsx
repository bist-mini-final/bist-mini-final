import { useState, useMemo, useEffect } from 'react';
import { ReactFlowProvider } from '@xyflow/react';
import { X } from 'lucide-react';
import { useBiPlaygroundHandoff } from '../bi/integrations/playgroundHandoffAdapter';
import { Header } from './components/Header';
import type { WorkflowOption } from './components/Header';
import { BenchmarkPanel } from './components/BenchmarkPanel';
import { PipelineCanvas } from './components/PipelineCanvas';
import { ModulePalette } from './components/Sidebar/ModulePalette';
import { usePipelineController } from './hooks/usePipelineController';
import { usePipelineGraph } from './hooks/usePipelineGraph';
import { useWorkflowPersistence } from './hooks/useWorkflowPersistence';
import { useResizablePanel } from './hooks/useResizablePanel';
import { ModuleExecutionContext } from './contexts/ModuleExecutionContext';
import { pipelineApi } from './services/api';
import './playground.css';

const DEFAULT_WORKFLOW_ID = 'default';

function PlaygroundWorkspace() {
  const [isPaletteOpen, setIsPaletteOpen] = useState(
    () => window.matchMedia('(min-width: 1024px)').matches
  );
  const modulePanel = useResizablePanel();
  const controller = usePipelineController();

  // Workflow list + active selection (default = "default" json)
  // Keep the canonical baseline selectable even while the workflow-list API is
  // starting up or temporarily unavailable. Previously an API failure left the
  // list empty, which also hid the selector entirely.
  const [workflows, setWorkflows] = useState<WorkflowOption[]>([
    { id: DEFAULT_WORKFLOW_ID, name: DEFAULT_WORKFLOW_ID },
  ]);
  const [activeWorkflowId, setActiveWorkflowId] = useState(DEFAULT_WORKFLOW_ID);
  const [isBenchmarkOpen, setIsBenchmarkOpen] = useState(false);
  const activeWorkflowName = useMemo(
    () => workflows.find((w) => w.id === activeWorkflowId)?.name ?? activeWorkflowId,
    [workflows, activeWorkflowId]
  );

  // Load workflow list on mount
  useEffect(() => {
    const controller = new AbortController();
    pipelineApi.listWorkflows(controller.signal).then(({ workflows: list }) => {
      const options: WorkflowOption[] = list.map((wf) => ({ id: wf.id, name: wf.name }));
      // Ensure "default" is always first in the list
      options.sort((a, b) => {
        if (a.id === DEFAULT_WORKFLOW_ID) return -1;
        if (b.id === DEFAULT_WORKFLOW_ID) return 1;
        return a.name.localeCompare(b.name);
      });
      setWorkflows(options);
    }).catch(() => {
      // The default option above remains available; a later refresh will add
      // the saved RAG workflows as soon as the backend is reachable.
    });
    return () => controller.abort();
  }, []);

  const graph = usePipelineGraph({
    queryText: controller.queryText,
    setQueryText: controller.setQueryText,
    activeStep: controller.activeStep,
    modules: controller.modules,
  });
  const workflow = useWorkflowPersistence(
    graph,
    controller.modules.length > 0,
    activeWorkflowId,
    activeWorkflowName,
  );
  useBiPlaygroundHandoff({
    modules: controller.modules,
    nodes: graph.nodes,
    ready: workflow.ready,
    search: window.location.search,
    setQueryText: controller.setQueryText,
  });
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

  const handleSelectWorkflow = (id: string) => {
    if (id === activeWorkflowId) return;
    // Reset local controller state when switching workflows
    controller.reset();
    graph.clearGraph();
    setActiveWorkflowId(id);
  };

  const refreshWorkflows = async () => {
    const { workflows: list } = await pipelineApi.listWorkflows();
    const options = list.map((item) => ({ id: item.id, name: item.name }));
    options.sort((a, b) => {
      if (a.id === DEFAULT_WORKFLOW_ID) return -1;
      if (b.id === DEFAULT_WORKFLOW_ID) return 1;
      return a.name.localeCompare(b.name);
    });
    setWorkflows(options);
  };

  const workflowIdFromName = (name: string) =>
    name.trim().toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '');

  const handleCreateWorkflow = () => {
    const name = window.prompt('새 워크플로 이름을 입력하세요.', '새 워크플로');
    if (!name?.trim()) return;
    const baseId = workflowIdFromName(name) || 'workflow';
    let id = baseId;
    let suffix = 2;
    while (workflows.some((item) => item.id === id)) id = `${baseId}-${suffix++}`;

    void pipelineApi.saveWorkflow(id, name.trim(), graph.exportGraph())
      .then(async () => {
        await refreshWorkflows();
        handleSelectWorkflow(id);
      })
      .catch((error: unknown) => controller.reportError(error instanceof Error ? error.message : '워크플로를 만들지 못했습니다.'));
  };

  const handleDuplicateWorkflow = () => {
    const source = activeWorkflowName;
    const name = window.prompt('복제할 워크플로 이름을 입력하세요.', `${source} 복사본`);
    if (!name?.trim()) return;
    const baseId = workflowIdFromName(name) || 'workflow-copy';
    let id = baseId;
    let suffix = 2;
    while (workflows.some((item) => item.id === id)) id = `${baseId}-${suffix++}`;

    void pipelineApi.saveWorkflow(id, name.trim(), graph.exportGraph())
      .then(async () => {
        await refreshWorkflows();
        handleSelectWorkflow(id);
      })
      .catch((error: unknown) => controller.reportError(error instanceof Error ? error.message : '워크플로를 복제하지 못했습니다.'));
  };

  const handleRenameWorkflow = () => {
    const name = window.prompt('워크플로 이름을 입력하세요.', activeWorkflowName);
    if (!name?.trim() || name.trim() === activeWorkflowName) return;
    void pipelineApi.saveWorkflow(activeWorkflowId, name.trim(), graph.exportGraph())
      .then(() => refreshWorkflows())
      .catch((error: unknown) => controller.reportError(error instanceof Error ? error.message : '워크플로 이름을 바꾸지 못했습니다.'));
  };

  const handleDeleteWorkflow = () => {
    if (activeWorkflowId === DEFAULT_WORKFLOW_ID || !window.confirm(`'${activeWorkflowName}' 워크플로를 삭제할까요?`)) return;
    void pipelineApi.deleteWorkflow(activeWorkflowId)
      .then(async () => {
        await refreshWorkflows();
        handleSelectWorkflow(DEFAULT_WORKFLOW_ID);
      })
      .catch((error: unknown) => controller.reportError(error instanceof Error ? error.message : '워크플로를 삭제하지 못했습니다.'));
  };

  const runMetrics = useMemo(() => {
    let totalElapsedMs = 0;
    let totalCostUsd = 0;
    let totalTokens = 0;
    let hasExecution = false;

    if (currentRun?.nodes) {
      Object.values(currentRun.nodes).forEach((nodeState) => {
        if (nodeState.elapsed_ms) {
          totalElapsedMs += nodeState.elapsed_ms;
          hasExecution = true;
        }
        if (nodeState.cost_usd) {
          totalCostUsd += nodeState.cost_usd;
        }
        if (nodeState.usage) {
          const tokens = nodeState.usage.total_tokens ?? nodeState.usage.tokens ?? 0;
          totalTokens += tokens;
        }
      });
    }

    graph.nodes.forEach((node) => {
      const data = node.data as Record<string, unknown> | undefined;
      if (data) {
        const ms = typeof data.elapsedMs === 'number' ? data.elapsedMs : typeof data.elapsed_ms === 'number' ? data.elapsed_ms : 0;
        const cost = typeof data.costUsd === 'number' ? data.costUsd : typeof data.cost_usd === 'number' ? data.cost_usd : 0;
        const usageObj = (data.usage as Record<string, number> | undefined) ?? (data.usage_metadata as Record<string, number> | undefined);
        const tokens = usageObj?.total_tokens ?? usageObj?.tokens ?? 0;

        if (!currentRun?.nodes?.[node.id]) {
          if (ms > 0) { totalElapsedMs += ms; hasExecution = true; }
          if (cost > 0) totalCostUsd += cost;
          if (tokens > 0) totalTokens += tokens;
        }
      }
    });

    return {
      totalElapsedMs,
      totalCostUsd,
      totalTokens,
      hasExecution: hasExecution || totalCostUsd > 0 || totalTokens > 0,
    };
  }, [currentRun, graph.nodes]);

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
          metrics={runMetrics}
          workflows={workflows}
          activeWorkflowId={activeWorkflowId}
          onSelectWorkflow={handleSelectWorkflow}
          onOpenBenchmark={() => setIsBenchmarkOpen(true)}
        />

        {controller.errorMessage && (
          <div className="error-banner" role="alert">
            <span>{controller.errorMessage}</span>
            <button onClick={controller.dismissError} aria-label="오류 메시지 닫기">
              <X className="h-4 w-4" />
            </button>
          </div>
        )}

        <main
          className="app-workspace"
          style={{ '--module-palette-width': `${modulePanel.width}px` } as React.CSSProperties}
        >
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
            workflows={workflows}
            activeWorkflowId={activeWorkflowId}
            onSelectWorkflow={handleSelectWorkflow}
            onCreateWorkflow={handleCreateWorkflow}
            onDuplicateWorkflow={handleDuplicateWorkflow}
            onRenameWorkflow={handleRenameWorkflow}
            onDeleteWorkflow={handleDeleteWorkflow}
          />
        </main>
        <BenchmarkPanel isOpen={isBenchmarkOpen} onClose={() => setIsBenchmarkOpen(false)} />
      </div>
    </ModuleExecutionContext.Provider>
  );
}

export function PlaygroundView() {
  return (
    <ReactFlowProvider>
      <PlaygroundWorkspace />
    </ReactFlowProvider>
  );
}
