import { useState, useMemo, useEffect } from 'react';
import { ReactFlowProvider } from '@xyflow/react';
import { X } from 'lucide-react';
import { IconButton, PromptDialog } from '../../shared/ui';
import { useBiPlaygroundHandoff } from '../bi/integrations/playgroundHandoffAdapter';
import { Header } from './components/Header';
import type { WorkflowOption } from './components/Header';
import { PipelineCanvas } from './components/PipelineCanvas';
import { ModulePalette } from './components/Sidebar/ModulePalette';
import { WorkflowTemplatePanel } from './components/WorkflowTemplatePanel';
import { usePipelineController } from './hooks/usePipelineController';
import { usePipelineGraph } from './hooks/usePipelineGraph';
import { useWorkflowPersistence } from './hooks/useWorkflowPersistence';
import { useResizablePanel } from './hooks/useResizablePanel';
import { ModuleExecutionContext } from './contexts/ModuleExecutionContext';
import { pipelineApi } from './services/api';
import type { WorkflowDocument } from './types';
import './playground.css';

const DEFAULT_WORKFLOW_ID = 'rag_query';

type WorkflowPrompt =
  | { readonly type: 'duplicate'; readonly initialValue: string }
  | { readonly type: 'template'; readonly templateId: string; readonly initialValue: string };

function workflowOptions(documents: WorkflowDocument[]): WorkflowOption[] {
  return documents
    .map((workflow) => ({
      id: workflow.id,
      name: workflow.name,
      kind: workflow.kind,
      editable: workflow.editable,
      template: workflow.template,
      nodeCount: workflow.graph.nodes.length,
      edgeCount: workflow.graph.edges.length,
      moduleTypes: workflow.graph.nodes.map((node) => node.module_type),
    }))
    .sort((left, right) => {
      if (left.id === DEFAULT_WORKFLOW_ID) return -1;
      if (right.id === DEFAULT_WORKFLOW_ID) return 1;
      return left.name.localeCompare(right.name);
    });
}

function PlaygroundWorkspace() {
  const [isPaletteOpen, setIsPaletteOpen] = useState(
    () => window.matchMedia('(min-width: 1024px)').matches
  );
  const modulePanel = useResizablePanel();
  const controller = usePipelineController();

  const [workflows, setWorkflows] = useState<WorkflowOption[]>([]);
  const [activeWorkflowId, setActiveWorkflowId] = useState(DEFAULT_WORKFLOW_ID);
  const [isTemplatePanelOpen, setIsTemplatePanelOpen] = useState(false);
  const [isWorkflowListLoading, setIsWorkflowListLoading] = useState(true);
  const [workflowPrompt, setWorkflowPrompt] = useState<WorkflowPrompt | null>(null);
  const [workflowPromptError, setWorkflowPromptError] = useState<string | null>(null);
  const [isCreatingWorkflow, setIsCreatingWorkflow] = useState(false);
  const activeWorkflow = useMemo(
    () => workflows.find((workflow) => workflow.id === activeWorkflowId),
    [workflows, activeWorkflowId]
  );
  const activeWorkflowName = activeWorkflow?.name ?? activeWorkflowId;
  const activeWorkflowEditable = activeWorkflow?.editable ?? false;

  // Load workflow list on mount
  useEffect(() => {
    const controller = new AbortController();
    pipelineApi.listWorkflows(controller.signal)
      .then(({ workflows: list }) => setWorkflows(workflowOptions(list)))
      .catch(() => undefined)
      .finally(() => setIsWorkflowListLoading(false));
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
    activeWorkflowEditable,
  );
  useBiPlaygroundHandoff({
    modules: controller.modules,
    nodes: graph.nodes,
    ready: workflow.ready,
    search: window.location.search,
    setQueryText: controller.setQueryText,
  });
  const currentRun = workflow.latestRunMatchesGraph ? workflow.latestRun : null;
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

  const handleNodeExecute = async (_nodeId: string) => {
    controller.dismissError();
    try {
      await workflow.executeAll(
        controller.queryText,
        controller.applyWorkflowRun
      );
    } catch (error: unknown) {
      if (!(error instanceof DOMException && error.name === 'AbortError')) {
        controller.reportError(
          error instanceof Error ? error.message : 'Kubernetes 워크플로 실행에 실패했습니다.'
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
    setWorkflows(workflowOptions(list));
  };

  const workflowIdFromName = (name: string) =>
    name.trim().toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '');

  const handleDuplicateWorkflow = () => {
    setWorkflowPromptError(null);
    setWorkflowPrompt({ type: 'duplicate', initialValue: `${activeWorkflowName} 복사본` });
  };

  const handleCreateFromTemplate = (templateId: string) => {
    const template = workflows.find(
      (item) => item.id === templateId && item.template,
    );
    if (!template) return;
    setWorkflowPromptError(null);
    setWorkflowPrompt({
      type: 'template',
      templateId,
      initialValue: `${template.name} 복사본`,
    });
  };

  const createWorkflow = async (name: string) => {
    const request = workflowPrompt;
    if (!request || isCreatingWorkflow) return;
    const baseId = workflowIdFromName(name)
      || (request.type === 'template' ? 'workflow-template' : 'workflow-copy');
    let id = baseId;
    let suffix = 2;
    while (workflows.some((item) => item.id === id)) id = `${baseId}-${suffix++}`;

    setIsCreatingWorkflow(true);
    setWorkflowPromptError(null);
    try {
      const workflowGraph = request.type === 'template'
        ? (await pipelineApi.getWorkflow(request.templateId)).graph
        : graph.exportGraph();
      await pipelineApi.saveWorkflow(id, name, workflowGraph);
      await refreshWorkflows();
      handleSelectWorkflow(id);
      setWorkflowPrompt(null);
      if (request.type === 'template') setIsTemplatePanelOpen(false);
    } catch (error: unknown) {
      setWorkflowPromptError(
        error instanceof Error ? error.message : '워크플로를 생성하지 못했습니다.'
      );
    } finally {
      setIsCreatingWorkflow(false);
    }
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
        <h1 className="page-visually-hidden">RAG 워크플로 플레이그라운드</h1>
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
          onSave={() => {
            if (!workflow.isEditableWorkflow) {
              handleDuplicateWorkflow();
              return;
            }
            void workflow.saveNow().catch(() => undefined);
          }}
          isClearingCache={workflow.isClearingCache}
          onClearCache={() => void handleClearCache()}
          metrics={runMetrics}
          workflows={workflows}
          activeWorkflowId={activeWorkflowId}
          onSelectWorkflow={handleSelectWorkflow}
          onOpenWorkflowCreator={() => setIsTemplatePanelOpen(true)}
        />

        {controller.errorMessage && (
          <div className="error-banner" role="alert">
            <span>{controller.errorMessage}</span>
            <IconButton size="sm" variant="ghost" className="error-banner__close" onClick={controller.dismissError} aria-label="오류 메시지 닫기">
              <X className="h-4 w-4" />
            </IconButton>
          </div>
        )}

        <section
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
              if (!workflow.isEditableWorkflow) {
                controller.reportError('표준 Job은 읽기 전용입니다. 워크플로를 복제한 뒤 편집하세요.');
                return;
              }
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
            currentRun={currentRun}
            isPaletteOpen={isPaletteOpen}
            onOpenPalette={() => setIsPaletteOpen(true)}
            activeWorkflowId={activeWorkflowId}
            readOnly={!workflow.isEditableWorkflow}
          />
        </section>
        <WorkflowTemplatePanel
          isOpen={isTemplatePanelOpen}
          isLoading={isWorkflowListLoading}
          workflows={workflows}
          modules={controller.modules}
          onClose={() => setIsTemplatePanelOpen(false)}
          onCreateFromTemplate={handleCreateFromTemplate}
        />
        <PromptDialog
          open={workflowPrompt !== null}
          title={workflowPrompt?.type === 'template' ? '템플릿으로 워크플로 만들기' : '워크플로 복제'}
          description={workflowPrompt?.type === 'template'
            ? '표준 템플릿을 편집 가능한 새 워크플로로 복제합니다.'
            : '현재 워크플로의 모듈과 연결 구성을 새 워크플로로 복제합니다.'}
          label="워크플로 이름"
          initialValue={workflowPrompt?.initialValue ?? ''}
          confirmLabel="워크플로 생성"
          busy={isCreatingWorkflow}
          error={workflowPromptError}
          onClose={() => {
            if (isCreatingWorkflow) return;
            setWorkflowPrompt(null);
            setWorkflowPromptError(null);
          }}
          onConfirm={(name) => { void createWorkflow(name); }}
        />
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
