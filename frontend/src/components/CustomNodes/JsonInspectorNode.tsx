import { lazy, Suspense, useCallback, useEffect, useMemo, useRef } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent, PointerEvent as ReactPointerEvent } from 'react';
import type { Node, NodeProps } from '@xyflow/react';
import { AlertCircle, Eye, Rows3 } from 'lucide-react';
import type { ModuleType } from '../../types';
import { formatJsonPreview } from '../../utils/jsonPreview';
import { getExecutionNodeState, NodeShell } from '../FlowNode/NodeShell';
import {
  adaptJsonInspectorContent,
  type JsonRow,
} from './jsonInspectorAdapters';

const JsonInspectorMarkdown = lazy(() => import('./JsonInspectorMarkdown'));

interface JsonInspectorNodeData extends Record<string, unknown> {
  executionState?: string;
  executionOutput?: unknown;
  executionInput?: unknown;
  executionError?: string;
  upstreamModuleType?: ModuleType;
  activeStep?: number;
  nodeWidth?: number;
  columnWidths?: Record<string, number>;
  onNodeWidthChange?: (width: number) => void;
  onColumnWidthChange?: (column: string, width: number) => void;
}

export type JsonInspectorNodeProps = NodeProps<Node<JsonInspectorNodeData>>;

const INDEX_COLUMN_WIDTH = 36;
const MIN_COLUMN_WIDTH = 96;
const MAX_COLUMN_WIDTH = 960;

function defaultColumnWidth(column: string): number {
  if (column === 'subquery' || column === 'query') return 260;
  if (column === 'embedding') return 520;
  return 180;
}

function sampleRows(rows: JsonRow[], count: number): JsonRow[] {
  const shuffled = [...rows];
  for (let index = shuffled.length - 1; index > 0; index -= 1) {
    const randomIndex = Math.floor(Math.random() * (index + 1));
    [shuffled[index], shuffled[randomIndex]] = [shuffled[randomIndex], shuffled[index]];
  }
  return shuffled.slice(0, Math.min(count, shuffled.length));
}

function formatCell(value: unknown): string {
  if (value === null) return 'null';
  if (value === undefined) return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'object') {
    return formatJsonPreview(value, {
      maxArrayItems: 6,
      maxDepth: 3,
      maxLines: 24,
      maxNodes: 40,
      maxObjectFields: 8,
      maxStringCharacters: 240,
      maxTextCharacters: 480,
    }).text.replace(/\s+/g, ' ');
  }
  return String(value);
}

export const JsonInspectorNode = ({ data, selected }: JsonInspectorNodeProps) => {
  const columnResizeCleanupRef = useRef<(() => void) | null>(null);
  const content = useMemo(() => {
    if (data.executionState !== 'succeeded') return null;
    return adaptJsonInspectorContent(data.upstreamModuleType, data.executionInput);
  }, [data.executionInput, data.executionState, data.upstreamModuleType]);
  const rows = content?.kind === 'table' ? content.rows : [];
  const previewRows = useMemo(() => sampleRows(rows, 5), [rows]);

  const columns = useMemo(
    () => {
      const available = Array.from(new Set(previewRows.flatMap((row) => Object.keys(row))));
      const preferred = content?.kind === 'table' ? content.preferredColumns : [];
      return [
        ...preferred.filter((column) => available.includes(column)),
        ...available.filter((column) => !preferred.includes(column)),
      ].slice(0, 5);
    },
    [content, previewRows]
  );

  const columnWidth = useCallback(
    (column: string) => data.columnWidths?.[column] ?? defaultColumnWidth(column),
    [data.columnWidths]
  );
  const tableWidth = useMemo(
    () => INDEX_COLUMN_WIDTH + columns.reduce((total, column) => total + columnWidth(column), 0),
    [columnWidth, columns]
  );

  const stopColumnResize = useCallback(() => {
    columnResizeCleanupRef.current?.();
    columnResizeCleanupRef.current = null;
  }, []);

  useEffect(() => stopColumnResize, [stopColumnResize]);

  const updateColumnWidth = useCallback(
    (column: string, width: number) => {
      data.onColumnWidthChange?.(
        column,
        Math.min(MAX_COLUMN_WIDTH, Math.max(MIN_COLUMN_WIDTH, Math.round(width)))
      );
    },
    [data.onColumnWidthChange]
  );

  const startColumnResize = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>, column: string) => {
      if (!data.onColumnWidthChange) return;
      event.preventDefault();
      event.stopPropagation();
      stopColumnResize();
      const startX = event.clientX;
      const startWidth = columnWidth(column);
      const handlePointerMove = (moveEvent: PointerEvent) => {
        updateColumnWidth(column, startWidth + moveEvent.clientX - startX);
      };
      const handlePointerUp = () => stopColumnResize();
      window.addEventListener('pointermove', handlePointerMove);
      window.addEventListener('pointerup', handlePointerUp);
      window.addEventListener('pointercancel', handlePointerUp);
      columnResizeCleanupRef.current = () => {
        window.removeEventListener('pointermove', handlePointerMove);
        window.removeEventListener('pointerup', handlePointerUp);
        window.removeEventListener('pointercancel', handlePointerUp);
      };
    },
    [columnWidth, data.onColumnWidthChange, stopColumnResize, updateColumnWidth]
  );

  const resizeColumnWithKeyboard = useCallback(
    (event: ReactKeyboardEvent<HTMLDivElement>, column: string) => {
      if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
      event.preventDefault();
      event.stopPropagation();
      updateColumnWidth(column, columnWidth(column) + (event.key === 'ArrowRight' ? 24 : -24));
    },
    [columnWidth, updateColumnWidth]
  );

  return (
    <NodeShell
      accent="#0284c7"
      icon={Eye}
      eyebrow="Output Module"
      title="JSON Data Inspector"
      state={getExecutionNodeState(data.executionState)}
      selected={selected}
      width={data.nodeWidth ?? 390}
      onWidthChange={data.onNodeWidthChange}
      minWidth={340}
      maxWidth={920}
      bodyClassName="space-y-2.5"
    >
      {data.executionState === 'failed' && data.executionError && (
        <div className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 p-2.5 text-[11px] text-rose-700">
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span className="break-words">{data.executionError}</span>
        </div>
      )}

      {(!content || (content.kind === 'table' && rows.length === 0))
        && data.executionState !== 'failed' && (
        <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 p-5 text-center">
          <Rows3 className="mx-auto h-5 w-5 text-sky-500" />
          <p className="mt-2 mb-0 text-xs font-semibold text-slate-700">상류 데이터 대기 중</p>
          <p className="mt-1 mb-0 text-[10px] text-slate-400">상류 JSON을 연결하고 실행하세요.</p>
        </div>
      )}

      {content?.kind === 'markdown' && (
        <Suspense
          fallback={(
            <div className="json-inspector-answer-loading" role="status">
              답변 형식을 불러오는 중…
            </div>
          )}
        >
          <JsonInspectorMarkdown content={content} />
        </Suspense>
      )}

      {content?.kind === 'table' && rows.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between text-[10px] text-slate-500">
            <span className="font-semibold text-slate-700">{content.label}</span>
            <span>전체 {content.totalRows}개 중 임의 {previewRows.length}개 · {columns.length}열</span>
          </div>
          <div className="nodrag nopan max-h-52 overflow-auto rounded-xl border border-slate-200 bg-white">
            <table
              className="table-fixed border-collapse text-left text-[10px]"
              style={{ width: `${tableWidth}px`, minWidth: '100%' }}
            >
              <colgroup>
                <col style={{ width: `${INDEX_COLUMN_WIDTH}px` }} />
                {columns.map((column) => (
                  <col key={column} style={{ width: `${columnWidth(column)}px` }} />
                ))}
              </colgroup>
              <thead className="sticky top-0 bg-slate-50 text-slate-500">
                <tr>
                  <th className="w-8 border-b border-slate-200 px-2 py-1.5 font-semibold">#</th>
                  {columns.map((column) => (
                    <th key={column} className="relative border-b border-slate-200 px-2 py-1.5 font-mono font-semibold">
                      <span className="block truncate" title={column}>{column}</span>
                      <div
                        className="nodrag nopan absolute top-0 right-0 z-10 h-full w-2 translate-x-1/2 cursor-col-resize touch-none outline-none after:absolute after:top-1 after:bottom-1 after:left-1/2 after:w-px after:bg-slate-300 hover:after:bg-sky-500 focus:after:bg-sky-500"
                        role="separator"
                        aria-label={`${column} 컬럼 너비 조절`}
                        aria-orientation="vertical"
                        aria-valuemin={MIN_COLUMN_WIDTH}
                        aria-valuemax={MAX_COLUMN_WIDTH}
                        aria-valuenow={columnWidth(column)}
                        tabIndex={0}
                        title={`${column} 컬럼 너비 조절`}
                        onPointerDown={(event) => startColumnResize(event, column)}
                        onKeyDown={(event) => resizeColumnWithKeyboard(event, column)}
                      />
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {previewRows.map((row, rowIndex) => (
                  <tr key={rowIndex} className="border-b border-slate-100 last:border-b-0">
                    <td className="px-2 py-1.5 font-mono text-slate-400">{rowIndex + 1}</td>
                    {columns.map((column) => {
                      const cell = formatCell(row[column]);
                      return (
                        <td key={column} className="overflow-hidden px-2 py-1.5 text-slate-700">
                          <span className="block truncate whitespace-nowrap" title={cell}>{cell}</span>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </NodeShell>
  );
};
