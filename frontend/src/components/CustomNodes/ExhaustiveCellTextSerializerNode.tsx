import type { Node, NodeProps } from '@xyflow/react';
import { LoaderCircle, Shuffle } from 'lucide-react';
import { getExecutionNodeState, NodeShell } from '../FlowNode/NodeShell';

interface ExhaustiveCellTextSerializerNodeData extends Record<string, unknown> {
  executionState?: string;
  executionOutput?: unknown;
  nodeWidth?: number;
  onNodeWidthChange?: (width: number) => void;
}

function outputSummary(output: unknown): { cells: number; documents: number } | null {
  if (!output || typeof output !== 'object' || Array.isArray(output)) return null;
  const items = (output as Record<string, unknown>).items;
  if (!Array.isArray(items)) return null;
  const cellIds = new Set(
    items.flatMap((item) => {
      if (!item || typeof item !== 'object' || Array.isArray(item)) return [];
      const cellId = (item as Record<string, unknown>).cell_id;
      return typeof cellId === 'string' ? [cellId] : [];
    }),
  );
  return { cells: cellIds.size, documents: items.length };
}

export type ExhaustiveCellTextSerializerNodeProps = NodeProps<
  Node<ExhaustiveCellTextSerializerNodeData>
>;

export const ExhaustiveCellTextSerializerNode = ({
  data,
  selected,
}: ExhaustiveCellTextSerializerNodeProps) => {
  const running = data.executionState === 'running';
  const summary = outputSummary(data.executionOutput);
  return (
    <NodeShell
      accent="#9333ea"
      icon={Shuffle}
      eyebrow="Transform Module"
      title="Exhaustive Cell Header Serializer"
      state={getExecutionNodeState(data.executionState)}
      nodeData={data}
      inputPorts={['input']}
      selected={selected}
      width={data.nodeWidth ?? 370}
      onWidthChange={data.onNodeWidthChange}
      bodyClassName="space-y-2.5"
    >
      <div className="rounded-xl border border-purple-100 bg-purple-50/70 px-3 py-2.5">
        <span className="block text-[9px] font-bold tracking-[0.1em] text-purple-700 uppercase">
          Deterministic · No model
        </span>
        <span className="mt-0.5 block truncate text-[10px] text-slate-600">
          Visible cell · Left headers × Above headers
        </span>
      </div>
      {running && (
        <div className="flex items-center gap-2 text-[10px] font-semibold text-purple-700" role="status">
          <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> 전체 헤더 조합 직렬화 중
        </div>
      )}
      {summary && (
        <div className="text-[10px] text-purple-800">
          대상 셀 <strong>{summary.cells}개</strong> · 조합 문서{' '}
          <strong>{summary.documents}개</strong>
        </div>
      )}
    </NodeShell>
  );
};
