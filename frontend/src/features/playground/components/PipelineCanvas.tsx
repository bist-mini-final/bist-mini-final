import { useCallback, useMemo, useState } from 'react';
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
import { AdaptiveQueryDecomposerNode } from './CustomNodes/AdaptiveQueryDecomposerNode';
import { DirectQueryDecomposerNode } from './CustomNodes/DirectQueryDecomposerNode';
import { BfsLlmStructureDetectorNode } from './CustomNodes/BfsLlmStructureDetectorNode';
import { CellTextSerializerNode } from './CustomNodes/CellTextSerializerNode';
import { ExhaustiveCellTextSerializerNode } from './CustomNodes/ExhaustiveCellTextSerializerNode';
import { CellTextEmbedderNode } from './CustomNodes/CellTextEmbedderNode';
import { DecomposerNode } from './CustomNodes/DecomposerNode';
import { EmbeddingNode } from './CustomNodes/EmbeddingNode';
import { DoclingTableDetectorNode } from './CustomNodes/DoclingTableDetectorNode';
import { GenericModuleNode } from './CustomNodes/GenericModuleNode';
import { LunaVlmStructureDetectorNode } from './CustomNodes/LunaVlmStructureDetectorNode';
import { OpenpyxlRegionDetectorNode } from './CustomNodes/OpenpyxlRegionDetectorNode';
import { ProcessedFileSelectorNode } from './CustomNodes/ProcessedFileSelectorNode';
import { PgVectorCollectionLoaderNode } from './CustomNodes/PgVectorCollectionLoaderNode';
import { PgVectorRetrieverNode } from './CustomNodes/PgVectorRetrieverNode';
import { PgVectorIndexWriterNode } from './CustomNodes/PgVectorIndexWriterNode';
import { QueryNode } from './CustomNodes/QueryNode';
import { ReaderNode } from './CustomNodes/ReaderNode';
import { RrfFusionNode } from './CustomNodes/RrfFusionNode';
import { SemanticQueryMatcherNode } from './CustomNodes/SemanticQueryMatcherNode';
import { LlmQueryRouterNode } from './CustomNodes/LlmQueryRouterNode';
import { SemanticScopedDenseRetrieverNode } from './CustomNodes/SemanticScopedDenseRetrieverNode';
import { ModuleSettingsModal } from './ModuleSettings/ModuleSettingsModal';
import { WorkflowLayersPanel } from './WorkflowLayersPanel';
import type { WorkflowOption } from './Header';
import type { usePipelineGraph } from '../hooks/usePipelineGraph';
import type { ModuleDefinition, WorkflowRun } from '../types';

type PipelineGraph = ReturnType<typeof usePipelineGraph>;

interface PipelineCanvasProps {
  graph: PipelineGraph;
  isPaletteOpen: boolean;
  onOpenPalette?: () => void;
  modules: ModuleDefinition[];
  runs: WorkflowRun[];
  workflows?: WorkflowOption[];
  activeWorkflowId?: string;
  onSelectWorkflow?: (id: string) => void;
  onCreateWorkflow?: () => void;
  onDuplicateWorkflow?: () => void;
  onRenameWorkflow?: () => void;
  onDeleteWorkflow?: () => void;
}

export function PipelineCanvas({
  graph,
  isPaletteOpen,
  modules,
  runs,
  workflows,
  activeWorkflowId,
  onSelectWorkflow,
  onCreateWorkflow,
  onDuplicateWorkflow,
  onRenameWorkflow,
  onDeleteWorkflow,
}: PipelineCanvasProps) {
  const [settingsNodeId, setSettingsNodeId] = useState<string | null>(null);
  const nodeTypes = useMemo<NodeTypes>(
    () => ({
      queryNode: QueryNode,
      direct_query_decomposer: DirectQueryDecomposerNode,
      decomposerNode: DecomposerNode,
      adaptive_query_decomposer: AdaptiveQueryDecomposerNode,
      embeddingNode: EmbeddingNode,
      cell_text_embedder: CellTextEmbedderNode,
      pgvector_index_writer: PgVectorIndexWriterNode,
      pgvector_collection_loader: PgVectorCollectionLoaderNode,
      pgvector_retriever: PgVectorRetrieverNode,
      rrf_fusion: RrfFusionNode,
      semantic_query_matcher: SemanticQueryMatcherNode,
      llm_query_router: LlmQueryRouterNode,
      semantic_scoped_dense_retriever: SemanticScopedDenseRetrieverNode,
      contextNode: ContextNode,
      readerNode: ReaderNode,
      processed_file_selector: ProcessedFileSelectorNode,
      bfs_llm_structure_detector: BfsLlmStructureDetectorNode,
      luna_vlm_structure_detector: LunaVlmStructureDetectorNode,
      docling_table_detector: DoclingTableDetectorNode,
      openpyxl_region_detector: OpenpyxlRegionDetectorNode,
      cell_text_serializer: CellTextSerializerNode,
      exhaustive_cell_text_serializer: ExhaustiveCellTextSerializerNode,
      generic_module: GenericModuleNode,
    }),
    []
  );
  const edgeTypes = useMemo<EdgeTypes>(() => ({ customEdge: CustomEdge }), []);
  const openModuleSettings = useCallback((nodeId: string) => setSettingsNodeId(nodeId), []);
  const settingsNode = settingsNodeId
    ? graph.nodes.find((node) => node.id === settingsNodeId)
    : undefined;
  const settingsModuleType = settingsNode
    ? (settingsNode.data.moduleType as string | undefined)
    : undefined;

  return (
    <ModuleSettingsContext.Provider value={{ openModuleSettings }}>
      <div className="relative h-full w-full bg-slate-900 overflow-hidden">
        <ReactFlow
          nodes={graph.nodes}
          edges={graph.edges}
          onNodesChange={graph.onNodesChange}
          onEdgesChange={graph.onEdgesChange}
          onConnect={graph.onConnect}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          fitView
          fitViewOptions={{ padding: 0.15, minZoom: 0.2, maxZoom: 1.5 }}
          deleteKeyCode={['Backspace', 'Delete']}
          snapToGrid
          snapGrid={[20, 20]}
          defaultEdgeOptions={{ type: 'customEdge' }}
          className="bg-dot-grid"
        >
          <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#334155" />
          <Controls className="bg-slate-800/90 border border-slate-700/80 rounded-xl fill-slate-300 stroke-slate-300 shadow-xl overflow-hidden backdrop-blur-md" />
          <MiniMap
            nodeColor={(node) =>
              NODE_COLORS[node.type || ''] ??
              (node.data?.moduleType
                ? NODE_COLORS[node.data.moduleType as string]
                : undefined) ??
              '#475569'
            }
            nodeStrokeWidth={3}
            maskColor="rgba(15, 23, 42, 0.75)"
            className="rounded-xl border border-slate-700/80 bg-slate-900/90 shadow-2xl overflow-hidden backdrop-blur-md"
            zoomable
            pannable
          />
        </ReactFlow>

        {workflows && activeWorkflowId && onSelectWorkflow && (
          <WorkflowLayersPanel
            workflows={workflows}
            activeWorkflowId={activeWorkflowId}
            onSelectWorkflow={onSelectWorkflow}
            onCreateWorkflow={onCreateWorkflow || (() => {})}
            onDuplicateWorkflow={onDuplicateWorkflow || (() => {})}
            onRenameWorkflow={onRenameWorkflow || (() => {})}
            onDeleteWorkflow={onDeleteWorkflow || (() => {})}
          />
        )}

        {settingsNode && (
          <ModuleSettingsModal
            isOpen={true}
            onClose={() => setSettingsNodeId(null)}
            nodeId={settingsNode.id}
            moduleType={settingsModuleType}
            initialValues={(settingsNode.data.config as Record<string, unknown>) ?? {}}
            onSave={(config) => {
              graph.updateNodeConfig(settingsNode.id, config);
              setSettingsNodeId(null);
            }}
          />
        )}
      </div>
    </ModuleSettingsContext.Provider>
  );
}
