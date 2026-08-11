export type ModuleType =
  | 'query_input'
  | 'decomposer'
  | 'embedder'
  | 'cell_text_embedder'
  | 'vector_index_writer'
  | 'bm25_retriever'
  | 'dense_retriever'
  | 'rrf_fusion'
  | 'context'
  | 'reader'
  | 'answer_cache_writer'
  | 'json_transformer'
  | 'json_inspector'
  | 'processed_file_selector'
  | 'bfs_llm_structure_detector'
  | 'local_vlm_structure_detector'
  | 'luna_vlm_structure_detector'
  | 'docling_table_detector'
  | 'openpyxl_region_detector'
  | 'cell_text_serializer'
  | 'exhaustive_cell_text_serializer';

export type ExecutionBranch = 'generated' | 'cached' | 'failed';
export type OutputBranch = Exclude<ExecutionBranch, 'failed'>;

export interface JsonSchema {
  $ref?: string;
  $defs?: Record<string, JsonSchema>;
  title?: string;
  description?: string;
  type?: string | string[];
  properties?: Record<string, JsonSchema>;
  required?: string[];
  items?: JsonSchema;
  anyOf?: JsonSchema[];
  enum?: unknown[];
  default?: unknown;
  minimum?: number;
  maximum?: number;
  exclusiveMinimum?: number;
  exclusiveMaximum?: number;
  minLength?: number;
  maxLength?: number;
  pattern?: string;
  format?: string;
  additionalProperties?: boolean | JsonSchema;
}

export interface ModuleDefinition {
  type: ModuleType;
  label: string;
  category: 'Source' | 'Logic' | 'Transform' | 'Output';
  description: string;
  inputs: string[];
  outputs: string[];
  branch_outputs: Partial<Record<OutputBranch, string>>;
  config_fields: string[];
  config_presets: Array<{
    id: string;
    label: string;
    values: Record<string, unknown>;
  }>;
  raw_input: boolean;
  raw_output: boolean;
  version: string;
  cacheable: boolean;
  input_schema: JsonSchema;
  config_schema: JsonSchema;
  output_schema: JsonSchema;
  branch_schemas: Partial<Record<OutputBranch, JsonSchema>>;
}

export interface ModulePresentation {
  icon: string;
  color: string;
}

export interface WorkflowPosition {
  x: number;
  y: number;
}

export interface WorkflowViewport extends WorkflowPosition {
  zoom: number;
}

export interface WorkflowNode {
  id: string;
  module_type: ModuleType;
  position: WorkflowPosition;
  config: Record<string, unknown>;
  values?: Record<string, unknown>;
  ui?: {
    width?: number | null;
    execution_stopped?: boolean;
    column_widths?: Record<string, number>;
  };
}

export interface WorkflowEdge {
  id: string;
  source: string;
  target: string;
  source_output?: string;
  target_input?: string;
  source_branch?: OutputBranch;
}

export interface WorkflowGraph {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  viewport: WorkflowViewport;
}

export interface WorkflowDocument {
  schema_version: number;
  id: string;
  name: string;
  updated_at: string;
  graph: WorkflowGraph;
}

export type RunStatus = 'queued' | 'running' | 'completed' | 'failed';
export type RunNodeStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'skipped';

export interface RunNodeState {
  node_id: string;
  module_type: ModuleType;
  batch_index: number;
  status: RunNodeStatus;
  input_payload: unknown;
  output: unknown;
  error: string | null;
  cache_key: string | null;
  cache_hit: boolean;
  outcome: ExecutionBranch | null;
  skip_reason: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface RunBatchState {
  index: number;
  node_ids: string[];
  status: 'pending' | 'running' | 'completed' | 'failed';
  started_at: string | null;
  completed_at: string | null;
}

export interface WorkflowRun {
  schema_version: number;
  id: string;
  workflow_id: string;
  workflow_updated_at: string;
  status: RunStatus;
  created_at: string;
  updated_at: string;
  graph: WorkflowGraph;
  runtime_inputs: Record<string, Record<string, unknown>>;
  use_cache: boolean;
  batches: RunBatchState[];
  nodes: Record<string, RunNodeState>;
}

export type SaveStatus = 'loading' | 'saving' | 'saved' | 'error';
