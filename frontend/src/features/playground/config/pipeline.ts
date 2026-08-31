import type { ModuleType } from '../types';

export const INITIAL_QUERY = '삼성전자 2023년 대비 2024년 영업이익 증가율은?';

export const PIPELINE_STAGES = [
  { id: 'query', label: '1. Query Input', color: '#107c41' },
  { id: 'decompose', label: '2. Decompose', color: '#7c3aed' },
  { id: 'embed', label: '3. Query Embed', color: '#0891b2' },
  { id: 'retrieve_keyword', label: '4a. Keyword Search', color: '#2563eb' },
  { id: 'retrieve_dense', label: '4b. Dense Search', color: '#0f766e' },
  { id: 'fuse', label: '5. RRF Fusion', color: '#059669' },
  { id: 'context', label: '6. Context Expand', color: '#d97706' },
  { id: 'read', label: '7. Answer Generate', color: '#e11d48' },
] as const;

export const MODULE_NODE_TYPES: Partial<Record<ModuleType, string>> = {
  query_input: 'queryNode',
  decomposer: 'decomposerNode',
  embedder: 'embeddingNode',
  cell_text_embedder: 'cell_text_embedder',
  pgvector_index_writer: 'pgvector_index_writer',
  pgvector_data_scope: 'pgvector_data_scope',
  pgvector_retriever: 'pgvector_retriever',
  postgres_native_keyword_retriever: 'postgres_native_keyword_retriever',
  rrf_fusion: 'rrf_fusion',
  pg_context_expander: 'contextNode',
  reader: 'readerNode',
  processed_file_selector: 'processed_file_selector',
  luna_vlm_structure_detector: 'luna_vlm_structure_detector',
  cell_text_serializer: 'cell_text_serializer',
};

export const NODE_MODULE_TYPES: Record<string, ModuleType> = Object.fromEntries(
  Object.entries(MODULE_NODE_TYPES)
    .filter(([, nodeType]) => nodeType !== 'generic_module')
    .map(([moduleType, nodeType]) => [nodeType, moduleType])
) as Record<string, ModuleType>;

export const NODE_COLORS: Record<string, string> = {
  queryNode: PIPELINE_STAGES[0].color,
  decomposerNode: PIPELINE_STAGES[1].color,
  embeddingNode: PIPELINE_STAGES[2].color,
  cell_text_embedder: '#0f766e',
  pgvector_index_writer: '#0f766e',
  pgvector_data_scope: '#0f766e',
  pgvector_retriever: '#0f766e',
  postgres_native_keyword_retriever: '#2563eb',
  rrf_fusion: PIPELINE_STAGES[5].color,
  contextNode: PIPELINE_STAGES[6].color,
  readerNode: PIPELINE_STAGES[7].color,
  processed_file_selector: '#107c41',
  luna_vlm_structure_detector: '#4338ca',
  cell_text_serializer: '#7c3aed',
  generic_module: '#64748b',
};
