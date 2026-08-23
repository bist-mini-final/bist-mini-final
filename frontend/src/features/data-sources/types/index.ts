import type { WorkflowRun } from '../../../shared/workflows/types';

export interface VectorIndexInfo {
  index_id: string;
  file_name: string;
  workbook_hash: string;
  company_name?: string;
  ticker?: string;
  model: string;
  dimension: number;
  document_count: number;
  created_at: string;
  total_size_bytes?: number;
  storage?: 'pgvector' | 'local';
  duration_seconds?: number;
  total_tokens?: number;
  estimated_cost_usd?: number;
  estimated_cost_krw?: number;
  batch_size?: number;
}

export interface DbStatusInfo {
  connected: boolean;
  host: string;
  port: number;
  database: string;
  postgres_version?: string;
  pgvector_version?: string;
  total_indexes: number;
  total_chunks: number;
  error?: string;
}

interface SerializedSampleItem {
  cell_id: string;
  sheet_name: string;
  cell_coord: string;
  row_header: string[];
  column_header: string[];
  cell_value: string;
  text: string;
}

export interface VectorIndexDetail {
  index_id: string;
  file_name: string;
  workbook_hash: string;
  company_name?: string;
  ticker?: string;
  model: string;
  dimension: number;
  document_count: number;
  sample_items: SerializedSampleItem[];
  duration_seconds?: number;
  total_tokens?: number;
  estimated_cost_usd?: number;
  estimated_cost_krw?: number;
  batch_size?: number;
  sheet_names?: string[];
  tables?: any[];
  luna_output?: any;
}

export interface LunaInspectionOutput {
  file_name: string;
  workbook_hash: string;
  sheet_names?: string[];
  tables?: unknown[];
  [key: string]: unknown;
}

export interface IngestionJobResponse {
  job_id: string;
  status: WorkflowRun['status'];
  workflow_id: string;
  run: WorkflowRun;
  index: VectorIndexInfo & {
    sheet_names?: string[];
    tables?: any[];
    luna_output?: LunaInspectionOutput;
  } | null;
  luna_output?: LunaInspectionOutput | null;
  target_index_id?: string | null;
  error?: string | null;
  worker_active: boolean;
}

export interface DeleteIngestionJobResponse {
  status: 'deleted';
  job_id: string;
  target_index_id?: string | null;
  index_deleted: boolean;
  source_file_preserved: boolean;
}

export interface SearchResultItem {
  score: number;
  cell_id: string;
  sheet_name: string;
  cell_coord: string;
  row_header: string[];
  column_header: string[];
  cell_value: string;
  text: string;
}

export interface SearchResponse {
  index_id: string;
  query: string;
  results: SearchResultItem[];
  total_results: number;
}
