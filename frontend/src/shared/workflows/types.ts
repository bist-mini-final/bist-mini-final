/** Backend-owned module identifier. Unknown types remain valid workflow nodes. */
export type ModuleType = string;

type ExecutionBranch = 'generated' | 'cached' | 'failed';
export type OutputBranch = Exclude<ExecutionBranch, 'failed'>;

interface WorkflowPosition {
  readonly x: number;
  readonly y: number;
}

export interface WorkflowViewport extends WorkflowPosition {
  readonly zoom: number;
}

interface WorkflowNode {
  readonly id: string;
  readonly module_type: ModuleType;
  readonly position: WorkflowPosition;
  readonly config: Record<string, unknown>;
  readonly values?: Record<string, unknown>;
  readonly ui?: {
    readonly width?: number | null;
    readonly height?: number | null;
    readonly execution_stopped?: boolean;
    readonly column_widths?: Record<string, number>;
  };
}

interface WorkflowEdge {
  readonly id: string;
  readonly source: string;
  readonly target: string;
  readonly source_output?: string;
  readonly target_input?: string;
  readonly source_branch?: OutputBranch;
}

export interface WorkflowGraph {
  readonly nodes: WorkflowNode[];
  readonly edges: WorkflowEdge[];
  readonly viewport: WorkflowViewport;
}

export interface WorkflowDocument {
  readonly schema_version: number;
  readonly id: string;
  readonly name: string;
  readonly updated_at: string;
  readonly graph: WorkflowGraph;
}

export type RunStatus = 'queued' | 'running' | 'paused' | 'completed' | 'failed';
type RunNodeStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'skipped';

interface RunNodeState {
  readonly node_id: string;
  readonly module_type: ModuleType;
  readonly batch_index: number;
  readonly status: RunNodeStatus;
  readonly input_payload: unknown;
  readonly config_payload: Record<string, unknown>;
  readonly output: unknown;
  readonly error: string | null;
  readonly cache_key: string | null;
  readonly cache_hit: boolean;
  readonly outcome: ExecutionBranch | null;
  readonly skip_reason: string | null;
  readonly started_at: string | null;
  readonly completed_at: string | null;
  readonly elapsed_ms?: number | null;
  readonly cost_usd?: number | null;
  readonly usage?: Record<string, number> | null;
  readonly progress?: Record<string, unknown>;
}

interface RunBatchState {
  readonly index: number;
  readonly node_ids: string[];
  readonly status: 'pending' | 'running' | 'completed' | 'failed';
  readonly started_at: string | null;
  readonly completed_at: string | null;
}

export interface WorkflowRun {
  readonly schema_version: number;
  readonly id: string;
  readonly workflow_id: string;
  readonly workflow_updated_at: string;
  readonly status: RunStatus;
  readonly orchestration?: {
    readonly backend: 'kubernetes';
    readonly deployment_name: string | null;
    readonly external_run_id: string | null;
    readonly submission_attempt: number;
    readonly submitted_at: string | null;
  };
  readonly created_at: string;
  readonly updated_at: string;
  readonly graph: WorkflowGraph;
  readonly runtime_inputs: Record<string, Record<string, unknown>>;
  readonly use_cache: boolean;
  readonly batches: RunBatchState[];
  readonly nodes: Record<string, RunNodeState>;
}
