export type SpreadsheetInspectorKind = 'luna_vlm';
export type SpreadsheetRegionKind = 'title' | 'column_header' | 'row_header' | 'data';

interface SpreadsheetCellBounds {
  min_row: number;
  max_row: number;
  min_column: number;
  max_column: number;
}

interface SpreadsheetResultRegion {
  region_id: string;
  type: SpreadsheetRegionKind;
  excel_range: string;
  bbox_px: [number, number, number, number];
  rows: [number, number];
  columns: [number, number];
}

export interface SpreadsheetHeaderNode {
  name: string;
  col_start: number;
  col_end: number;
  row_start: number;
  row_end: number;
  children: SpreadsheetHeaderNode[];
}

export interface SpreadsheetResultTable {
  sheet_name: string;
  table_index: number;
  excel_range: string;
  bbox_px?: [number, number, number, number];
  cell_bounds?: SpreadsheetCellBounds;
  regions: SpreadsheetResultRegion[];
  header_tree: SpreadsheetHeaderNode[];
}

export interface SpreadsheetResult {
  fileName: string;
  workbookHash: string;
  sheetNames: string[];
  tables: SpreadsheetResultTable[];
}

function objectValue(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function numberTuple(value: unknown): [number, number, number, number] | undefined {
  if (!Array.isArray(value) || value.length !== 4 || value.some((item) => typeof item !== 'number')) {
    return undefined;
  }
  return [value[0], value[1], value[2], value[3]];
}

function numberPair(value: unknown): [number, number] | undefined {
  if (!Array.isArray(value) || value.length !== 2 || value.some((item) => typeof item !== 'number')) {
    return undefined;
  }
  return [value[0], value[1]];
}

function parseRegion(value: unknown): SpreadsheetResultRegion | null {
  const record = objectValue(value);
  if (!record) return null;
  const type = record.type;
  const bbox = numberTuple(record.bbox_px);
  const rows = numberPair(record.rows);
  const columns = numberPair(record.columns);
  if (
    !['title', 'column_header', 'row_header', 'data'].includes(String(type))
    || typeof record.region_id !== 'string'
    || typeof record.excel_range !== 'string'
    || !bbox
    || !rows
    || !columns
  ) return null;
  return {
    region_id: record.region_id,
    type: type as SpreadsheetRegionKind,
    excel_range: record.excel_range,
    bbox_px: bbox,
    rows,
    columns,
  };
}

function parseCellBounds(value: unknown): SpreadsheetCellBounds | undefined {
  const record = objectValue(value);
  if (!record) return undefined;
  const entries = ['min_row', 'max_row', 'min_column', 'max_column'] as const;
  if (entries.some((field) => typeof record[field] !== 'number')) return undefined;
  return {
    min_row: record.min_row as number,
    max_row: record.max_row as number,
    min_column: record.min_column as number,
    max_column: record.max_column as number,
  };
}

function parseHeaderNode(value: unknown): SpreadsheetHeaderNode | null {
  const record = objectValue(value);
  if (!record) return null;
  const numericFields = ['col_start', 'col_end', 'row_start', 'row_end'] as const;
  if (
    typeof record.name !== 'string'
    || numericFields.some((field) => typeof record[field] !== 'number')
  ) return null;
  return {
    name: record.name,
    col_start: record.col_start as number,
    col_end: record.col_end as number,
    row_start: record.row_start as number,
    row_end: record.row_end as number,
    children: (Array.isArray(record.children) ? record.children : []).flatMap((child) => {
      const parsed = parseHeaderNode(child);
      return parsed ? [parsed] : [];
    }),
  };
}

export function parseSpreadsheetResult(input: unknown, output: unknown): SpreadsheetResult | null {
  const outputRecord = objectValue(output);
  if (!outputRecord) return null;
  const workbookHash = outputRecord.workbook_hash;
  const fileName = outputRecord.file_name;
  if (typeof workbookHash !== 'string' || typeof fileName !== 'string') return null;

  const tables = (Array.isArray(outputRecord.tables) ? outputRecord.tables : []).flatMap((value) => {
    const record = objectValue(value);
    if (
      !record
      || typeof record.sheet_name !== 'string'
      || typeof record.table_index !== 'number'
      || typeof record.excel_range !== 'string'
    ) return [];
    return [{
      sheet_name: record.sheet_name,
      table_index: record.table_index,
      excel_range: record.excel_range,
      bbox_px: numberTuple(record.bbox_px),
      cell_bounds: parseCellBounds(record.cell_bounds),
      regions: (Array.isArray(record.regions) ? record.regions : []).flatMap((region) => {
        const parsed = parseRegion(region);
        return parsed ? [parsed] : [];
      }),
      header_tree: (Array.isArray(record.header_tree) ? record.header_tree : []).flatMap((node) => {
        const parsed = parseHeaderNode(node);
        return parsed ? [parsed] : [];
      }),
    } satisfies SpreadsheetResultTable];
  });

  const inputRecord = objectValue(input);
  const configuredSheets = Array.isArray(inputRecord?.sheet_names)
    ? inputRecord.sheet_names.filter((value): value is string => typeof value === 'string')
    : [];
  const sheetNames = Array.from(new Set([
    ...configuredSheets,
    ...tables.map((table) => table.sheet_name),
  ]));
  return { fileName, workbookHash, sheetNames, tables };
}

export function spreadsheetTableKey(table: SpreadsheetResultTable): string {
  return `${table.sheet_name}:${table.table_index}`;
}

export function spreadsheetColumnLetter(column: number): string {
  let value = column;
  let result = '';
  while (value > 0) {
    const remainder = (value - 1) % 26;
    result = String.fromCharCode(65 + remainder) + result;
    value = Math.floor((value - 1) / 26);
  }
  return result || 'A';
}
