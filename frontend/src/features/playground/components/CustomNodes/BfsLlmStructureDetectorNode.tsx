import { useState } from 'react';
import type { Node, NodeProps } from '@xyflow/react';
import { LoaderCircle, Network } from 'lucide-react';
import { getExecutionNodeState, NodeShell } from '../FlowNode/NodeShell';
import { SpreadsheetInspectAction } from '../SpreadsheetResults/SpreadsheetInspectAction';
import { SpreadsheetResultModal } from '../SpreadsheetResults/SpreadsheetResultModal';


interface BfsLlmStructureDetectorNodeData extends Record<string, unknown> {
  executionState?: string;
  executionInput?: unknown;
  executionOutput?: unknown;
  nodeWidth?: number;
  config?: {
    model?: string;
    header_candidate_rows?: number;
    merge_gap?: number;
  };
  onNodeWidthChange?: (width: number) => void;
}

export type BfsLlmStructureDetectorNodeProps = NodeProps<Node<BfsLlmStructureDetectorNodeData>>;

function tableCount(output: unknown): number | null {
  if (!output || typeof output !== 'object' || Array.isArray(output)) return null;
  const tables = (output as Record<string, unknown>).tables;
  return Array.isArray(tables) ? tables.length : null;
}

export const BfsLlmStructureDetectorNode = ({
  data,
  selected,
}: BfsLlmStructureDetectorNodeProps) => {
  const [isInspectorOpen, setIsInspectorOpen] = useState(false);
  const detectedTables = tableCount(data.executionOutput);
  const running = data.executionState === 'running';
  const model = data.config?.model ?? 'gpt-5.6-luna';
  const candidateRows = data.config?.header_candidate_rows ?? 10;

  return (
    <>
      <NodeShell
        accent="#0f766e"
        icon={Network}
        eyebrow="Logic Module"
        title="BFS + LLM Table Structure Detector"
        state={getExecutionNodeState(data.executionState)}
        nodeData={data}
        inputPorts={['input']}
        selected={selected}
        width={data.nodeWidth ?? 370}
        onWidthChange={data.onNodeWidthChange}
        bodyClassName="space-y-2.5"
        headerActions={(
          <SpreadsheetInspectAction
            available={detectedTables !== null}
            label="BFS + LLM 구조 식별 결과 보기"
            onInspect={() => setIsInspectorOpen(true)}
          />
        )}
      >
        <div className="rounded-xl border border-teal-100 bg-teal-50/70 px-3 py-2.5">
          <span className="block text-[9px] font-bold tracking-[0.12em] text-teal-700 uppercase">
            4-way BFS → Boundary LLM → Header Tree
          </span>
          <span className="mt-0.5 block truncate text-[10px] text-slate-600" title={model}>
            {model} · 상단 {candidateRows}행만 판정
          </span>
        </div>
        {running && (
          <div className="flex items-center gap-2 rounded-lg border border-teal-200 bg-white px-2.5 py-2 text-[10px] font-semibold text-teal-800" role="status">
            <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> 표 분리 및 계층 구조 판정 중
          </div>
        )}
        {detectedTables !== null && (
          <div className="rounded-lg border border-teal-100 bg-white px-2.5 py-2 text-[10px] text-teal-800">
            구조화된 테이블 <strong>{detectedTables}개</strong>
          </div>
        )}
      </NodeShell>
      {isInspectorOpen && (
        <SpreadsheetResultModal
          kind="bfs_llm"
          input={data.executionInput}
          output={data.executionOutput}
          onClose={() => setIsInspectorOpen(false)}
        />
      )}
    </>
  );
};
