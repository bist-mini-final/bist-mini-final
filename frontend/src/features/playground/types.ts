/** Backend-owned module identifier. Unknown types render with GenericModuleNode. */
export type ModuleType = string;

type ExecutionBranch = 'generated' | 'cached' | 'failed';
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
  task: {
    engine: 'kubernetes';
    enabled: boolean;
    retries: number;
    retry_delay_seconds: number;
    timeout_seconds: number | null;
    tags: string[];
    resource_profile: 'interactive' | 'standard' | 'high-memory' | 'gpu';
  };
  input_schema: JsonSchema;
  config_schema: JsonSchema;
  output_schema: JsonSchema;
  execution_schema: JsonSchema;
  documentation_url: string;
  branch_schemas: Partial<Record<OutputBranch, JsonSchema>>;
}

export interface ModulePresentation {
  icon: string;
  color: string;
}

interface WorkflowPosition {
  x: number;
  y: number;
}

export interface WorkflowViewport extends WorkflowPosition {
  zoom: number;
}

interface WorkflowNode {
  id: string;
  module_type: ModuleType;
  position: WorkflowPosition;
  config: Record<string, unknown>;
  values?: Record<string, unknown>;
  ui?: {
    width?: number | null;
    height?: number | null;
    execution_stopped?: boolean;
    column_widths?: Record<string, number>;
  };
}

interface WorkflowEdge {
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

type RunStatus = 'queued' | 'running' | 'paused' | 'completed' | 'failed';
type RunNodeStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'skipped';

interface RunNodeState {
  node_id: string;
  module_type: ModuleType;
  batch_index: number;
  status: RunNodeStatus;
  input_payload: unknown;
  config_payload: Record<string, unknown>;
  output: unknown;
  error: string | null;
  cache_key: string | null;
  cache_hit: boolean;
  outcome: ExecutionBranch | null;
  skip_reason: string | null;
  started_at: string | null;
  completed_at: string | null;
  elapsed_ms?: number | null;
  cost_usd?: number | null;
  usage?: Record<string, number> | null;
  progress?: Record<string, unknown>;
}

interface RunBatchState {
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
  orchestration?: {
    backend: 'direct' | 'kubernetes';
    deployment_name: string | null;
    external_run_id: string | null;
    submission_attempt: number;
    submitted_at: string | null;
  };
  created_at: string;
  updated_at: string;
  graph: WorkflowGraph;
  runtime_inputs: Record<string, Record<string, unknown>>;
  use_cache: boolean;
  batches: RunBatchState[];
  nodes: Record<string, RunNodeState>;
}

export interface BenchmarkCase {
  id: string;
  question: string;
  expected_numbers?: number[];
  expected_terms?: string[];
  expected_target?: string;
  expected_sheets?: string[];
  expected_abstain?: boolean;
  expected_plan?: { metrics?: string[]; periods?: number[] };
}

export interface BenchmarkSet {
  id: string;
  name: string;
  cases: BenchmarkCase[];
}

export interface BenchmarkSummary {
  workflow_id: string;
  cases: number;
  scored_cases: number;
  accuracy: number | null;
  average_latency_seconds: number;
  average_tokens: number;
  average_cost_usd: number;
  average_reused_tokens: number;
  average_reused_cost_usd: number;
  cache_hits: number;
  node_runs: number;
  llm_fallback_calls: number;
  plan_reuse_count?: number;
  plan_reuse_coverage?: number | null;
  plan_cases?: number;
  plan_accuracy?: number | null;
  plan_reuse_precision?: number | null;
  unsafe_plan_reuse_count?: number;
  sheet_cases?: number;
  sheet_exact_accuracy?: number | null;
  average_sheet_precision?: number | null;
  average_sheet_recall?: number | null;
  intermediate_cases?: number;
  intermediate_accuracy?: number | null;
  errors: number;
  route_cases: number;
  route_accuracy: number | null;
  route_attempts?: number;
  route_abstentions?: number;
  route_coverage?: number | null;
  route_precision?: number | null;
  abstention_cases?: number;
  abstention_accuracy?: number | null;
  router_kind: string | null;
  average_router_latency_seconds: number | null;
  average_router_tokens: number | null;
  average_router_cost_usd: number | null;
}

export interface BenchmarkComparison {
  id?: string;
  saved_at?: string;
  execution_mode: 'sequential_isolated';
  execution_scope?: 'full' | 'pre_retrieval';
  use_cache: boolean;
  cache_mode?: 'off' | 'all' | 'index_only';
  summary: BenchmarkSummary[];
  results: Array<{
    workflow_id: string;
    case_id: string;
    question: string;
    latency_seconds: number;
    total_tokens: number;
    estimated_cost_usd: number;
    score: { scored: boolean; correct: boolean | null };
    route_score: { correct: boolean; target_correct: boolean; sheets_correct: boolean; expected_abstain?: boolean } | null;
    plan_score?: {
      correct: boolean;
      metrics_correct: boolean;
      metric_precision?: number;
      metric_recall?: number;
      periods_correct: boolean;
      source: string | null;
    } | null;
    sheet_score?: {
      correct: boolean;
      precision: number;
      recall: number;
      expected: string[];
      actual: string[];
    } | null;
    intermediate_score?: { correct: boolean; checks: Record<string, boolean> } | null;
    router: {
      kind: string;
      target: string | null;
      sheets: string[];
      matched: boolean;
      latency_seconds: number;
      total_tokens: number;
      estimated_cost_usd: number;
    } | null;
    error: string | null;
    timeline: Array<{ module_type: string; latency_seconds: number | null }>;
  }>;
}

export interface BenchmarkJob {
  id: string;
  status: 'queued' | 'running' | 'pausing' | 'paused' | 'cancelling' | 'completed' | 'cancelled' | 'failed';
  completed: number;
  total: number;
  current: { workflow_id?: string; case_id?: string; question?: string; run_id?: string | null } | null;
  active_run: BenchmarkRunSnapshot | null;
  last_run: BenchmarkRunSnapshot | null;
  logs: Array<{
    at: string;
    event: 'started' | 'running' | 'completed' | 'pausing' | 'paused' | 'resumed' | 'cancelling';
    completed: number;
    total: number;
    workflow_id?: string;
    case_id?: string;
    question?: string;
    run_id?: string | null;
    error?: string | null;
    run?: BenchmarkRunSnapshot | null;
  }>;
  result: BenchmarkComparison | null;
  error: string | null;
}

export interface BenchmarkRunSnapshot {
  id: string;
  status: string;
  nodes: Array<{
    node_id: string;
    module_type: string;
    status: string;
    elapsed_ms: number | null;
    cache_hit: boolean;
    error: string | null;
    output_preview: string;
  }>;
}

export type SaveStatus = 'loading' | 'saving' | 'saved' | 'error';
