export type DataSourceFileType = 'excel' | 'parquet' | 'json' | 'other';

export interface DataSourceFile {
  file_name: string;
  size_bytes: number;
  updated_at: string;
  file_type: DataSourceFileType;
  sheet_names: string[];
  workbook_hash: string;
  associated_index_ids: string[];
}

export interface VectorIndexInfo {
  index_id: string;
  file_name: string;
  workbook_hash: string;
  model: string;
  dimension: number;
  document_count: number;
  created_at: string;
  total_size_bytes?: number;
  storage?: 'pgvector' | 'local';
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

export interface SerializedSampleItem {
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
  model: string;
  dimension: number;
  document_count: number;
  sample_items: SerializedSampleItem[];
}

export interface IngestRequest {
  file_name: string;
  model: string;
  variant_mode: 'header_only' | 'header_with_value' | 'both';
  sheet_names?: string[];
  batch_size?: number;
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

export interface SheetPreviewData {
  file_name: string;
  sheet_name: string;
  available_sheets: string[];
  total_sheets: number;
  preview_rows: string[][];
}
