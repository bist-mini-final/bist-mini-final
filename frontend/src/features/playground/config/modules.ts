import type { ModuleDefinition, ModulePresentation, ModuleType } from '../types';

const PREFERRED_CATEGORY_ORDER = [
  'Source',
  'Logic',
  'Transform',
  'Storage / DB',
  'Output',
] as const;

export function orderedModuleCategories(modules: ModuleDefinition[]): string[] {
  const available = new Set(modules.map((module) => module.category));
  const preferred = PREFERRED_CATEGORY_ORDER.filter((category) => available.delete(category));
  return [...preferred, ...Array.from(available).sort()];
}

/** UI-only metadata. Labels, descriptions, and I/O contracts come from the backend. */
export const MODULE_PRESENTATION: Partial<Record<ModuleType, ModulePresentation>> = {
  query_input: { icon: 'MessageSquare', color: '#107c41' },
  decomposer: { icon: 'GitBranch', color: '#7c3aed' },
  embedder: { icon: 'Cpu', color: '#0891b2' },
  cell_text_embedder: { icon: 'Binary', color: '#0f766e' },
  pgvector_index_writer: { icon: 'Database', color: '#0f766e' },
  pgvector_collection_loader: { icon: 'Database', color: '#0f766e' },
  pgvector_retriever: { icon: 'Search', color: '#0f766e' },
  postgres_native_keyword_retriever: { icon: 'ListFilter', color: '#2563eb' },
  semantic_query_matcher: { icon: 'Route', color: '#7c3aed' },
  llm_query_router: { icon: 'Bot', color: '#c026d3' },
  rrf_fusion: { icon: 'Merge', color: '#059669' },
  pg_context_expander: { icon: 'Maximize2', color: '#d97706' },
  reader: { icon: 'Sparkles', color: '#e11d48' },
  processed_file_selector: { icon: 'FileSpreadsheet', color: '#107c41' },
  luna_vlm_structure_detector: { icon: 'CloudCog', color: '#4338ca' },
  company_entity_extractor: { icon: 'Building2', color: '#7c3aed' },
  cell_text_serializer: { icon: 'Rows3', color: '#7c3aed' },
  sheet_metadata_persistence: { icon: 'TableProperties', color: '#d97706' },
  qa_example_loader: { icon: 'MessageSquare', color: '#d97706' },
};
