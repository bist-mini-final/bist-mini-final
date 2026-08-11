import { useState } from 'react';
import type { Node, NodeProps } from '@xyflow/react';
import { Image, LoaderCircle, ScanSearch } from 'lucide-react';
import { getExecutionNodeState, NodeShell } from '../FlowNode/NodeShell';
import { SpreadsheetInspectAction } from '../SpreadsheetResults/SpreadsheetInspectAction';
import { SpreadsheetResultModal } from '../SpreadsheetResults/SpreadsheetResultModal';


interface DoclingTableDetectorNodeData extends Record<string, unknown> {
  executionState?: string;
  executionInput?: unknown;
  executionOutput?: unknown;
  nodeWidth?: number;
  config?: {
    max_rows?: number;
    max_columns?: number;
  };
  onNodeWidthChange?: (width: number) => void;
}

export type DoclingTableDetectorNodeProps = NodeProps<Node<DoclingTableDetectorNodeData>>;

function outputSummary(output: unknown): { sheets: number; tables: number } | null {
  if (!output || typeof output !== 'object' || Array.isArray(output)) return null;
  const tables = (output as Record<string, unknown>).tables;
  if (!Array.isArray(tables)) return null;
  const sheetNames = new Set(
    tables.flatMap((table) => {
      if (!table || typeof table !== 'object' || Array.isArray(table)) return [];
      const sheetName = (table as Record<string, unknown>).sheet_name;
      return typeof sheetName === 'string' ? [sheetName] : [];
    }),
  );
  return { sheets: sheetNames.size, tables: tables.length };
}

export const DoclingTableDetectorNode = ({ data, selected }: DoclingTableDetectorNodeProps) => {
  const [isInspectorOpen, setIsInspectorOpen] = useState(false);
  const maxRows = data.config?.max_rows ?? 400;
  const maxColumns = data.config?.max_columns ?? 60;
  const summary = outputSummary(data.executionOutput);
  const running = data.executionState === 'running';

  return (
    <>
      <NodeShell
        accent="#0891b2"
        icon={ScanSearch}
        eyebrow="Logic Module"
        title="Docling Table Region Detector"
        state={getExecutionNodeState(data.executionState)}
        selected={selected}
        width={data.nodeWidth ?? 340}
        onWidthChange={data.onNodeWidthChange}
        bodyClassName="space-y-2.5"
        headerActions={(
          <SpreadsheetInspectAction
            available={summary !== null}
            label="Docling 감지 결과 보기"
            onInspect={() => setIsInspectorOpen(true)}
          />
        )}
      >
        <div className="flex items-center gap-2 rounded-xl border border-cyan-100 bg-cyan-50/70 px-3 py-2.5">
          <Image className="h-4 w-4 shrink-0 text-cyan-700" />
          <div className="min-w-0">
            <span className="block text-[9px] font-bold tracking-[0.12em] text-cyan-700 uppercase">Excel → PNG → Docling</span>
            <span className="block text-[10px] text-slate-600">최대 {maxRows}행 × {maxColumns}열</span>
          </div>
        </div>
        {running && (
          <div className="flex items-center gap-2 rounded-lg border border-cyan-200 bg-white px-2.5 py-2 text-[10px] font-semibold text-cyan-800" role="status">
            <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> 시트 렌더링 및 테이블 탐지 중
          </div>
        )}
        {summary && (
          <div className="rounded-lg border border-cyan-100 bg-white px-2.5 py-2 text-[10px] text-cyan-800">
            시트 <strong>{summary.sheets}개</strong> · 테이블 <strong>{summary.tables}개</strong> 추출
          </div>
        )}
      </NodeShell>
      {isInspectorOpen && (
        <SpreadsheetResultModal
          kind="docling"
          input={data.executionInput}
          output={data.executionOutput}
          onClose={() => setIsInspectorOpen(false)}
        />
      )}
    </>
  );
};
