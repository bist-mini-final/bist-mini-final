import type { ModuleType, OutputBranch } from '../../shared/workflows/types';

export type {
  ModuleType,
  OutputBranch,
  RunStatus,
  WorkflowDocument,
  WorkflowGraph,
  WorkflowRun,
  WorkflowViewport,
} from '../../shared/workflows/types';

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
  category: string;
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

export type SaveStatus = 'loading' | 'saving' | 'saved' | 'error';
