import type { Edge, Node } from '@xyflow/react';
import type { ModuleType } from '../types';

export const INITIAL_QUERY = '';

const PIPELINE_STAGES = [
  { id: 'query', nodeType: 'queryNode', color: '#107c41', width: 320 },
  { id: 'decompose', nodeType: 'decomposerNode', color: '#7c3aed', width: 320 },
  { id: 'embedding', nodeType: 'embeddingNode', color: '#0891b2', width: 300 },
  { id: 'bm25', nodeType: 'bm25_retriever', color: '#2563eb', width: 330 },
  { id: 'dense', nodeType: 'dense_retriever', color: '#0891b2', width: 330 },
  { id: 'rrf', nodeType: 'rrf_fusion', color: '#059669', width: 350 },
  { id: 'context', nodeType: 'contextNode', color: '#d97706', width: 320 },
  { id: 'reader', nodeType: 'readerNode', color: '#e11d48', width: 360 },
] as const;

/** Optional specialized renderers; all other backend modules use generic_module. */
export const MODULE_NODE_TYPES: Partial<Record<ModuleType, string>> = {
  query_input: 'queryNode',
  direct_query_decomposer: 'direct_query_decomposer',
  decomposer: 'decomposerNode',
  adaptive_query_decomposer: 'adaptive_query_decomposer',
  template_query_decomposer: 'template_query_decomposer',
  embedder: 'embeddingNode',
  cell_text_embedder: 'cell_text_embedder',
  vector_index_writer: 'vector_index_writer',
  bm25_retriever: 'bm25_retriever',
  dense_retriever: 'dense_retriever',
  rrf_fusion: 'rrf_fusion',
  semantic_query_matcher: 'semantic_query_matcher',
  llm_query_router: 'llm_query_router',
  semantic_scoped_dense_retriever: 'semantic_scoped_dense_retriever',
  context: 'contextNode',
  reader: 'readerNode',
  answer_cache_writer: 'answer_cache_writer',
  json_transformer: 'json_transformer',
  json_inspector: 'json_inspector',
  processed_file_selector: 'processed_file_selector',
  bfs_llm_structure_detector: 'bfs_llm_structure_detector',
  local_vlm_structure_detector: 'local_vlm_structure_detector',
  luna_vlm_structure_detector: 'luna_vlm_structure_detector',
  docling_table_detector: 'docling_table_detector',
  openpyxl_region_detector: 'openpyxl_region_detector',
  cell_text_serializer: 'cell_text_serializer',
  exhaustive_cell_text_serializer: 'exhaustive_cell_text_serializer',
  prebuilt_index_loader: 'prebuilt_index_loader',
  pgvector_index_writer: 'pgvector_index_writer',
  pgvector_collection_loader: 'pgvector_collection_loader',
  pgvector_retriever: 'pgvector_retriever',
  semantic_scoped_pgvector_retriever: 'semantic_scoped_pgvector_retriever',
};

export const NODE_MODULE_TYPES: Record<string, ModuleType> = Object.fromEntries(
  Object.entries(MODULE_NODE_TYPES)
    .filter(([, nodeType]) => nodeType !== 'generic_module')
    .map(([moduleType, nodeType]) => [nodeType, moduleType])
) as Record<string, ModuleType>;

export const NODE_COLORS: Record<string, string> = {
  queryNode: PIPELINE_STAGES[0].color,
  direct_query_decomposer: '#475569',
  decomposerNode: PIPELINE_STAGES[1].color,
  adaptive_query_decomposer: '#6d28d9',
  template_query_decomposer: '#4f46e5',
  embeddingNode: PIPELINE_STAGES[2].color,
  cell_text_embedder: '#0f766e',
  vector_index_writer: '#0f766e',
  prebuilt_index_loader: '#059669',
  pgvector_index_writer: '#0f766e',
  pgvector_collection_loader: '#0f766e',
  pgvector_retriever: '#0f766e',
  semantic_scoped_pgvector_retriever: '#0f766e',
  bm25_retriever: PIPELINE_STAGES[3].color,
  dense_retriever: PIPELINE_STAGES[4].color,
  rrf_fusion: PIPELINE_STAGES[5].color,
  semantic_query_matcher: '#7c3aed',
  llm_query_router: '#c026d3',
  semantic_scoped_dense_retriever: '#0f766e',
  contextNode: PIPELINE_STAGES[6].color,
  readerNode: PIPELINE_STAGES[7].color,
  answer_cache_writer: '#be123c',
  json_transformer: '#7c3aed',
  json_inspector: '#0284c7',
  processed_file_selector: '#107c41',
  bfs_llm_structure_detector: '#0f766e',
  local_vlm_structure_detector: '#4f46e5',
  luna_vlm_structure_detector: '#4338ca',
  docling_table_detector: '#0891b2',
  openpyxl_region_detector: '#d97706',
  cell_text_serializer: '#7c3aed',
  exhaustive_cell_text_serializer: '#9333ea',
  generic_module: '#64748b',
};

export function createInitialNodes(): Node[] {
  return [
    { id: 'stage-0', type: 'queryNode', position: { x: 80, y: 80 }, data: {} },
    { id: 'stage-1', type: 'decomposerNode', position: { x: 480, y: 80 }, data: {} },
    { id: 'stage-2', type: 'embeddingNode', position: { x: 1320, y: 80 }, data: {} },
    { id: 'stage-3', type: 'bm25_retriever', position: { x: 2160, y: 180 }, data: {} },
    { id: 'stage-4', type: 'dense_retriever', position: { x: 2580, y: 520 }, data: {} },
    { id: 'stage-5', type: 'rrf_fusion', position: { x: 3000, y: 340 }, data: {} },
    { id: 'stage-6', type: 'contextNode', position: { x: 3420, y: 340 }, data: {} },
    { id: 'stage-7', type: 'readerNode', position: { x: 3860, y: 340 }, data: {} },
    { id: 'stage-8', type: 'answer_cache_writer', position: { x: 4280, y: 340 }, data: {} },
    { id: 'excel-0', type: 'processed_file_selector', position: { x: 80, y: 620 }, data: {} },
    { id: 'excel-structure', type: 'local_vlm_structure_detector', position: { x: 480, y: 620 }, data: {} },
    { id: 'excel-1', type: 'docling_table_detector', position: { x: 480, y: 1040 }, data: {} },
    { id: 'excel-2', type: 'openpyxl_region_detector', position: { x: 900, y: 1040 }, data: {} },
    { id: 'excel-3', type: 'cell_text_serializer', position: { x: 900, y: 620 }, data: {} },
    { id: 'excel-4', type: 'cell_text_embedder', position: { x: 1320, y: 620 }, data: {} },
    { id: 'excel-5', type: 'vector_index_writer', position: { x: 1740, y: 620 }, data: {} },
    { id: 'excel-bfs-alternative', type: 'bfs_llm_structure_detector', position: { x: 480, y: 1460 }, data: {} },
  ];
}

export function createInitialEdges(): Edge[] {
  return [
    {
      id: 'stage-edge-query-decompose',
      source: 'stage-0',
      target: 'stage-1',
      sourceHandle: 'generated',
      targetHandle: 'query_context',
      type: 'customEdge',
      data: { active: false, done: false, color: '#107c41', source_branch: 'generated', source_output: 'query_context', target_input: 'query_context' },
    },
    { id: 'stage-edge-decompose-embed', source: 'stage-1', target: 'stage-2', sourceHandle: 'out', targetHandle: 'input', type: 'customEdge', data: { active: false, done: false, color: '#7c3aed', source_output: 'output', target_input: 'input' } },
    { id: 'stage-edge-decompose-bm25', source: 'stage-1', target: 'stage-3', sourceHandle: 'out', targetHandle: 'query_input', type: 'customEdge', data: { active: false, done: false, color: '#7c3aed', source_output: 'output', target_input: 'query_input' } },
    { id: 'stage-edge-embed-dense', source: 'stage-2', target: 'stage-4', sourceHandle: 'out', targetHandle: 'query_input', type: 'customEdge', data: { active: false, done: false, color: '#0891b2', source_output: 'output', target_input: 'query_input' } },
    { id: 'stage-edge-file-structure', source: 'excel-0', target: 'excel-structure', sourceHandle: 'out', targetHandle: 'input', type: 'customEdge', data: { active: false, done: false, color: '#107c41', source_output: 'output', target_input: 'input' } },
    { id: 'stage-edge-structure-serializer', source: 'excel-structure', target: 'excel-3', sourceHandle: 'out', targetHandle: 'input', type: 'customEdge', data: { active: false, done: false, color: '#0f766e', source_output: 'output', target_input: 'input' } },
    { id: 'stage-edge-file-docling', source: 'excel-0', target: 'excel-1', sourceHandle: 'out', targetHandle: 'input', type: 'customEdge', data: { active: false, done: false, color: '#107c41', source_output: 'output', target_input: 'input' } },
    { id: 'stage-edge-docling-openpyxl', source: 'excel-1', target: 'excel-2', sourceHandle: 'out', targetHandle: 'input', type: 'customEdge', data: { active: false, done: false, color: '#0891b2', source_output: 'output', target_input: 'input' } },
    { id: 'stage-edge-documents-bm25', source: 'excel-3', target: 'stage-3', sourceHandle: 'out', targetHandle: 'document_input', type: 'customEdge', data: { active: false, done: false, color: '#7c3aed', source_output: 'output', target_input: 'document_input' } },
    { id: 'stage-edge-documents-embed', source: 'excel-3', target: 'excel-4', sourceHandle: 'out', targetHandle: 'input', type: 'customEdge', data: { active: false, done: false, color: '#7c3aed', source_output: 'output', target_input: 'input' } },
    { id: 'stage-edge-document-embeddings-index', source: 'excel-4', target: 'excel-5', sourceHandle: 'out', targetHandle: 'input', type: 'customEdge', data: { active: false, done: false, color: '#0f766e', source_output: 'output', target_input: 'input' } },
    { id: 'stage-edge-index-dense', source: 'excel-5', target: 'stage-4', sourceHandle: 'out', targetHandle: 'index_input', type: 'customEdge', data: { active: false, done: false, color: '#0f766e', source_output: 'index_output', target_input: 'index_input' } },
    { id: 'stage-edge-bm25-rrf', source: 'stage-3', target: 'stage-5', sourceHandle: 'out', targetHandle: 'bm25_result', type: 'customEdge', data: { active: false, done: false, color: '#2563eb', source_output: 'bm25_result', target_input: 'bm25_result' } },
    { id: 'stage-edge-dense-rrf', source: 'stage-4', target: 'stage-5', sourceHandle: 'out', targetHandle: 'dense_result', type: 'customEdge', data: { active: false, done: false, color: '#0891b2', source_output: 'dense_result', target_input: 'dense_result' } },
    { id: 'stage-edge-rrf-context', source: 'stage-5', target: 'stage-6', sourceHandle: 'out', targetHandle: 'retrieval_json', type: 'customEdge', data: { active: false, done: false, color: '#059669', source_output: 'retrieval_json', target_input: 'retrieval_json' } },
    { id: 'stage-edge-documents-context', source: 'excel-3', target: 'stage-6', sourceHandle: 'out', targetHandle: 'document_input', type: 'customEdge', data: { active: false, done: false, color: '#7c3aed', source_output: 'output', target_input: 'document_input' } },
    { id: 'stage-edge-context-reader', source: 'stage-6', target: 'stage-7', sourceHandle: 'out', targetHandle: 'context_json', type: 'customEdge', data: { active: false, done: false, color: '#d97706', source_output: 'context_json', target_input: 'context_json' } },
    { id: 'stage-edge-reader-cache', source: 'stage-7', target: 'stage-8', sourceHandle: 'out', targetHandle: 'answer_json', type: 'customEdge', data: { active: false, done: false, color: '#e11d48', source_output: 'answer_json', target_input: 'answer_json' } },
  ];
}
