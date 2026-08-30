import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  type EdgeTypes,
  type NodeTypes,
} from '@xyflow/react';
import { NODE_COLORS, NODE_MODULE_TYPES } from '../config/pipeline';
import { ModuleSettingsContext } from '../contexts/ModuleSettingsContext';
import { CustomEdge } from './CustomEdge';
import { ContextNode } from './CustomNodes/ContextNode';
import { CellTextSerializerNode } from './CustomNodes/CellTextSerializerNode';
import { CellTextEmbedderNode } from './CustomNodes/CellTextEmbedderNode';
import { DecomposerNode } from './CustomNodes/DecomposerNode';
import { EmbeddingNode } from './CustomNodes/EmbeddingNode';
import { GenericModuleNode } from './CustomNodes/GenericModuleNode';
import { LunaVlmStructureDetectorNode } from './CustomNodes/LunaVlmStructureDetectorNode';
import { ProcessedFileSelectorNode } from './CustomNodes/ProcessedFileSelectorNode';
import { PgVectorDataScopeNode } from './CustomNodes/PgVectorDataScopeNode';
import { PgVectorRetrieverNode } from './CustomNodes/PgVectorRetrieverNode';
import { PgVectorIndexWriterNode } from './CustomNodes/PgVectorIndexWriterNode';
import { QueryNode } from './CustomNodes/QueryNode';
import { ReaderNode } from './CustomNodes/ReaderNode';
import { RrfFusionNode } from './CustomNodes/RrfFusionNode';
import { SemanticQueryMatcherNode } from './CustomNodes/SemanticQueryMatcherNode';
import { LlmQueryRouterNode } from './CustomNodes/LlmQueryRouterNode';
import { ModuleSettingsModal } from './ModuleSettings/ModuleSettingsModal';
import type { usePipelineGraph } from '../hooks/usePipelineGraph';
import type { ModuleDefinition, WorkflowRun } from '../types';

type PipelineGraph = ReturnType<typeof usePipelineGraph>;

interface PipelineCanvasProps {
  graph: PipelineGraph;
  isPaletteOpen: boolean;
  onOpenPalette?: () => void;
  modules: ModuleDefinition[];
  currentRun: WorkflowRun | null;
  activeWorkflowId: string;
  readOnly: boolean;
}

export function PipelineCanvas({
  graph,
  isPaletteOpen,
  modules,
  currentRun,
  activeWorkflowId,
  readOnly,
}: PipelineCanvasProps) {
  const [settingsNodeId, setSettingsNodeId] = useState<string | null>(null);
  const nodeTypes = useMemo<NodeTypes>(
    () => ({
      queryNode: QueryNode,
      decomposerNode: DecomposerNode,
      embeddingNode: EmbeddingNode,
      cell_text_embedder: CellTextEmbedderNode,
      pgvector_index_writer: PgVectorIndexWriterNode,
      pgvector_data_scope: PgVectorDataScopeNode,
      pgvector_retriever: PgVectorRetrieverNode,
      postgres_native_keyword_retriever: GenericModuleNode,
      rrf_fusion: RrfFusionNode,
      semantic_query_matcher: SemanticQueryMatcherNode,
      llm_query_router: LlmQueryRouterNode,
      contextNode: ContextNode,
      readerNode: ReaderNode,
      processed_file_selector: ProcessedFileSelectorNode,
      luna_vlm_structure_detector: LunaVlmStructureDetectorNode,
      cell_text_serializer: CellTextSerializerNode,
      generic_module: GenericModuleNode,
    }),
    []
  );
  const edgeTypes = useMemo<EdgeTypes>(() => ({ customEdge: CustomEdge }), []);
  const openModuleSettings = useCallback(
    (nodeId: string) => setSettingsNodeId(nodeId),
    [],
  );
  useEffect(() => setSettingsNodeId(null), [activeWorkflowId]);
  const settingsNode = settingsNodeId
    ? graph.nodes.find((node) => node.id === settingsNodeId)
    : undefined;
  const settingsModuleType = settingsNode
    ? (settingsNode.data.moduleType as string | undefined)
      ?? NODE_MODULE_TYPES[settingsNode.type ?? '']
    : undefined;
  const settingsModule = settingsModuleType
    ? modules.find((module) => module.type === settingsModuleType)
    : undefined;
  return (
    <ModuleSettingsContext.Provider value={openModuleSettings}>
      <section className="pipeline-canvas" data-palette-open={isPaletteOpen} aria-label="RAG 파이프라인 편집 캔버스">
        <div className="canvas-hint">
          <span>{readOnly ? '표준 Job · 편집하려면 워크플로를 복제하세요' : '휠로 확대 · 빈 영역 드래그로 이동'}</span>
        </div>
        <ReactFlow
          key={activeWorkflowId}
          nodes={graph.nodes}
          edges={graph.edges}
          onNodesChange={readOnly ? graph.onReadOnlyNodesChange : graph.onNodesChange}
          onEdgesChange={readOnly ? undefined : graph.onEdgesChange}
          onConnect={readOnly ? undefined : graph.onConnect}
          connectOnClick
          onInit={graph.onInit}
          onMoveEnd={graph.onMoveEnd}
          onDrop={readOnly ? undefined : graph.onDrop}
          onDragOver={readOnly ? undefined : graph.onDragOver}
          onNodeClick={(_, node) => graph.selectNode(node.id)}
          selectionOnDrag
          selectionKeyCode="Shift"
          multiSelectionKeyCode="Shift"
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          fitView
          fitViewOptions={{ padding: 0.16 }}
          minZoom={0.2}
          maxZoom={1.6}
          defaultEdgeOptions={{ type: 'customEdge' }}
          proOptions={{ hideAttribution: true }}
          nodesDraggable={!readOnly}
          nodesConnectable={!readOnly}
          deleteKeyCode={readOnly ? null : ['Backspace', 'Delete']}
          edgesFocusable={true}
        >
          <Background variant={BackgroundVariant.Dots} gap={24} size={1.4} color="#cbd5e1" />
          <Controls position="bottom-right" showInteractive={false} />
          <MiniMap
            position="bottom-left"
            nodeColor={(node) => NODE_COLORS[node.type ?? ''] ?? '#64748b'}
            zoomable
            pannable
          />
        </ReactFlow>
      </section>
      {settingsNode && settingsModule && (
        <ModuleSettingsModal
          nodeId={settingsNode.id}
          definition={settingsModule}
          config={(settingsNode.data.config as Record<string, unknown> | undefined) ?? {}}
          onConfigChange={(patch) => graph.updateNodeConfig(settingsNode.id, patch)}
          readOnly={readOnly}
          run={currentRun}
          onClose={() => setSettingsNodeId(null)}
        />
      )}
    </ModuleSettingsContext.Provider>
  );
}
