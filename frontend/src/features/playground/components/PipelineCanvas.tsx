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
import { AnswerCacheWriterNode } from './CustomNodes/AnswerCacheWriterNode';
import { AdaptiveQueryDecomposerNode } from './CustomNodes/AdaptiveQueryDecomposerNode';
import { Bm25RetrieverNode } from './CustomNodes/Bm25RetrieverNode';
import { BfsLlmStructureDetectorNode } from './CustomNodes/BfsLlmStructureDetectorNode';
import { CellTextSerializerNode } from './CustomNodes/CellTextSerializerNode';
import { ExhaustiveCellTextSerializerNode } from './CustomNodes/ExhaustiveCellTextSerializerNode';
import { CellTextEmbedderNode } from './CustomNodes/CellTextEmbedderNode';
import { VectorIndexWriterNode } from './CustomNodes/VectorIndexWriterNode';
import { DecomposerNode } from './CustomNodes/DecomposerNode';
import { DirectQueryDecomposerNode } from './CustomNodes/DirectQueryDecomposerNode';
import { DenseRetrieverNode } from './CustomNodes/DenseRetrieverNode';
import { EmbeddingNode } from './CustomNodes/EmbeddingNode';
import { DoclingTableDetectorNode } from './CustomNodes/DoclingTableDetectorNode';
import { JsonInspectorNode } from './CustomNodes/JsonInspectorNode';
import { JsonTransformerNode } from './CustomNodes/JsonTransformerNode';
import { GenericModuleNode } from './CustomNodes/GenericModuleNode';
import { LocalVlmStructureDetectorNode } from './CustomNodes/LocalVlmStructureDetectorNode';
import { LunaVlmStructureDetectorNode } from './CustomNodes/LunaVlmStructureDetectorNode';
import { OpenpyxlRegionDetectorNode } from './CustomNodes/OpenpyxlRegionDetectorNode';
import { ProcessedFileSelectorNode } from './CustomNodes/ProcessedFileSelectorNode';
import { PrebuiltIndexLoaderNode } from './CustomNodes/PrebuiltIndexLoaderNode';
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
  workflows: WorkflowOption[];
  activeWorkflowId: string;
  onSelectWorkflow: (id: string) => void;
  onCreateWorkflow: () => void;
  onDuplicateWorkflow: () => void;
  onRenameWorkflow: () => void;
  onDeleteWorkflow: () => void;
}

export function PipelineCanvas({
  graph,
  isPaletteOpen,
  modules,
  runs,
  workflows, activeWorkflowId, onSelectWorkflow, onCreateWorkflow, onDuplicateWorkflow, onRenameWorkflow, onDeleteWorkflow,
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
      vector_index_writer: VectorIndexWriterNode,
      pgvector_index_writer: PgVectorIndexWriterNode,
      pgvector_collection_loader: PgVectorCollectionLoaderNode,
      pgvector_retriever: PgVectorRetrieverNode,
      bm25_retriever: Bm25RetrieverNode,
      dense_retriever: DenseRetrieverNode,
      rrf_fusion: RrfFusionNode,
      semantic_query_matcher: SemanticQueryMatcherNode,
      llm_query_router: LlmQueryRouterNode,
      semantic_scoped_dense_retriever: SemanticScopedDenseRetrieverNode,
      contextNode: ContextNode,
      readerNode: ReaderNode,
      answer_cache_writer: AnswerCacheWriterNode,
      json_transformer: JsonTransformerNode,
      json_inspector: JsonInspectorNode,
      processed_file_selector: ProcessedFileSelectorNode,
      prebuilt_index_loader: PrebuiltIndexLoaderNode,
      bfs_llm_structure_detector: BfsLlmStructureDetectorNode,
      local_vlm_structure_detector: LocalVlmStructureDetectorNode,
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
      ?? NODE_MODULE_TYPES[settingsNode.type ?? '']
    : undefined;
  const settingsModule = settingsModuleType
    ? modules.find((module) => module.type === settingsModuleType)
    : undefined;
  const settingsPreview = undefined;

  return (
    <ModuleSettingsContext.Provider value={openModuleSettings}>
      <section className="pipeline-canvas" data-palette-open={isPaletteOpen} aria-label="RAG 파이프라인 편집 캔버스">
        <div className="canvas-hint">
          <span>휠로 확대 · 빈 영역 드래그로 이동</span>
        </div>
        <ReactFlow
        key={activeWorkflowId}
        nodes={graph.nodes}
        edges={graph.edges}
        onNodesChange={graph.onNodesChange}
        onEdgesChange={graph.onEdgesChange}
        onConnect={graph.onConnect}
        connectOnClick
        onInit={graph.onInit}
        onMoveEnd={graph.onMoveEnd}
        onDrop={graph.onDrop}
        onDragOver={graph.onDragOver}
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
        deleteKeyCode={['Backspace', 'Delete']}
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
        <WorkflowLayersPanel nodes={graph.nodes} edges={graph.edges} modules={modules} workflows={workflows} activeWorkflowId={activeWorkflowId} onSelectWorkflow={onSelectWorkflow} onCreateWorkflow={onCreateWorkflow} onDuplicateWorkflow={onDuplicateWorkflow} onRenameWorkflow={onRenameWorkflow} onDeleteWorkflow={onDeleteWorkflow} onSelectNode={graph.selectNode} onDuplicateNode={graph.duplicateNode} />
      </section>
      {settingsNode && settingsModule && (
        <ModuleSettingsModal
          nodeId={settingsNode.id}
          definition={settingsModule}
          config={(settingsNode.data.config as Record<string, unknown> | undefined) ?? {}}
          onConfigChange={(patch) => graph.updateNodeConfig(settingsNode.id, patch)}
          runs={runs}
          preview={settingsPreview}
          onClose={() => setSettingsNodeId(null)}
        />
      )}
    </ModuleSettingsContext.Provider>
  );
}
