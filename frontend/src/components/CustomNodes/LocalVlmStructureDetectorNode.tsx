import { useState } from 'react';
import type { Node, NodeProps } from '@xyflow/react';
import { LoaderCircle, ScanText } from 'lucide-react';
import { getExecutionNodeState, NodeShell } from '../FlowNode/NodeShell';
import { SpreadsheetInspectAction } from '../SpreadsheetResults/SpreadsheetInspectAction';
import { SpreadsheetResultModal } from '../SpreadsheetResults/SpreadsheetResultModal';


interface LocalVlmStructureDetectorNodeData extends Record<string, unknown> {
  executionState?: string;
  executionInput?: unknown;
  executionOutput?: unknown;
  nodeWidth?: number;
  config?: {
    model?: string;
    max_rows?: number;
    max_columns?: number;
    max_context_cells?: number;
    validation_retries?: number;
  };
  onNodeWidthChange?: (width: number) => void;
}

export type LocalVlmStructureDetectorNodeProps = NodeProps<Node<LocalVlmStructureDetectorNodeData>>;

function tableCount(output: unknown): number | null {
  if (!output || typeof output !== 'object' || Array.isArray(output)) return null;
  const tables = (output as Record<string, unknown>).tables;
  return Array.isArray(tables) ? tables.length : null;
}

export const LocalVlmStructureDetectorNode = ({
  data,
  selected,
}: LocalVlmStructureDetectorNodeProps) => {
  const [isInspectorOpen, setIsInspectorOpen] = useState(false);
  const detectedTables = tableCount(data.executionOutput);
  const running = data.executionState === 'running';
  const model = data.config?.model ?? 'qwen3-vl:4b-instruct';
  const maxCells = data.config?.max_context_cells ?? 15000;

  return (
    <>
      <NodeShell
        accent="#4f46e5"
        icon={ScanText}
        eyebrow="Logic Module"
        title="Local VLM Table Structure Detector"
        state={getExecutionNodeState(data.executionState)}
      nodeData={data}
        selected={selected}
        width={data.nodeWidth ?? 380}
        onWidthChange={data.onNodeWidthChange}
        bodyClassName="space-y-2.5"
        headerActions={(
          <SpreadsheetInspectAction
            available={detectedTables !== null}
            label="Local VLM 구조 식별 결과 보기"
            onInspect={() => setIsInspectorOpen(true)}
          />
        )}
      >
        <div className="rounded-xl border border-indigo-100 bg-indigo-50/70 px-3 py-2.5">
          <span className="block text-[9px] font-bold tracking-[0.12em] text-indigo-700 uppercase">
            Typed Cells + Coordinates → Local Vision
          </span>
          <span className="mt-0.5 block truncate text-[10px] text-slate-600" title={model}>
            {model} · 최대 {maxCells.toLocaleString()} cells/sheet
          </span>
        </div>
        {running && (
          <div className="flex items-center gap-2 rounded-lg border border-indigo-200 bg-white px-2.5 py-2 text-[10px] font-semibold text-indigo-800" role="status">
            <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> 로컬 멀티모달 시트 분석 중
          </div>
        )}
        {detectedTables !== null && (
          <div className="rounded-lg border border-indigo-100 bg-white px-2.5 py-2 text-[10px] text-indigo-800">
            구조화된 테이블 <strong>{detectedTables}개</strong>
          </div>
        )}
      </NodeShell>
      {isInspectorOpen && (
        <SpreadsheetResultModal
          kind="local_vlm"
          input={data.executionInput}
          output={data.executionOutput}
          onClose={() => setIsInspectorOpen(false)}
        />
      )}
    </>
  );
};
