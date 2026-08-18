import type { ModulePresentation, ModuleType } from '../types';

export const MODULE_CATEGORIES = ['Source', 'Logic', 'Transform', 'Output'] as const;

/** UI-only metadata. Labels, descriptions, and I/O contracts come from the backend. */
export const MODULE_PRESENTATION: Partial<Record<ModuleType, ModulePresentation>> = {
  query_input: { icon: 'MessageSquare', color: '#107c41' },
  direct_query_decomposer: { icon: 'ArrowRight', color: '#475569' },
  decomposer: { icon: 'GitBranch', color: '#7c3aed' },
  adaptive_query_decomposer: { icon: 'GitBranch', color: '#6d28d9' },
  embedder: { icon: 'Cpu', color: '#0891b2' },
  cell_text_embedder: { icon: 'Binary', color: '#0f766e' },
  vector_index_writer: { icon: 'Database', color: '#0f766e' },
  bm25_retriever: { icon: 'ListFilter', color: '#2563eb' },
  dense_retriever: { icon: 'Search', color: '#0891b2' },
  rrf_fusion: { icon: 'Merge', color: '#059669' },
  semantic_query_matcher: { icon: 'Route', color: '#7c3aed' },
  llm_query_router: { icon: 'Bot', color: '#c026d3' },
  semantic_scoped_dense_retriever: { icon: 'SearchCheck', color: '#0f766e' },
  context: { icon: 'Maximize2', color: '#d97706' },
  reader: { icon: 'Sparkles', color: '#e11d48' },
  answer_cache_writer: { icon: 'ArchiveRestore', color: '#be123c' },
  json_transformer: { icon: 'FileCode', color: '#7c3aed' },
  json_inspector: { icon: 'Eye', color: '#0284c7' },
  processed_file_selector: { icon: 'FileSpreadsheet', color: '#107c41' },
  bfs_llm_structure_detector: { icon: 'Network', color: '#0f766e' },
  local_vlm_structure_detector: { icon: 'ScanText', color: '#4f46e5' },
  luna_vlm_structure_detector: { icon: 'CloudCog', color: '#4338ca' },
  docling_table_detector: { icon: 'ScanSearch', color: '#0891b2' },
  openpyxl_region_detector: { icon: 'TableProperties', color: '#d97706' },
  cell_text_serializer: { icon: 'Rows3', color: '#7c3aed' },
  exhaustive_cell_text_serializer: { icon: 'Shuffle', color: '#9333ea' },
  prebuilt_index_loader: { icon: 'FolderArchive', color: '#059669' },
  dataframe_source: { icon: 'TableProperties', color: '#2563eb' },
  image_tile_source: { icon: 'Layers', color: '#7c3aed' },
  qa_example_loader: { icon: 'MessageSquare', color: '#d97706' },
};
