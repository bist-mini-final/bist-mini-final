import type { Node, NodeProps } from '@xyflow/react';
import { LoaderCircle, Rows3 } from 'lucide-react';
import { getExecutionNodeState, NodeShell } from '../FlowNode/NodeShell';

interface CellTextSerializerNodeData extends Record<string, unknown> {
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

export type CellTextSerializerNodeProps = NodeProps<Node<CellTextSerializerNodeData>>;

export const CellTextSerializerNode = ({ data, selected }: CellTextSerializerNodeProps) => {
  const running = data.executionState === 'running';
  const summary = outputSummary(data.executionOutput);
  return (
    <NodeShell
      accent="#7c3aed"
      icon={Rows3}
      eyebrow="Transform Module"
      title="Structured Cell Text Serializer"
      state={getExecutionNodeState(data.executionState)}
      selected={selected}
      width={data.nodeWidth ?? 370}
      onWidthChange={data.onNodeWidthChange}
      bodyClassName="space-y-2.5"
    >
      <div className="rounded-xl border border-violet-100 bg-violet-50/70 px-3 py-2.5">
        <span className="block text-[9px] font-bold tracking-[0.1em] text-violet-700 uppercase">Structured Cell v5</span>
        <span className="mt-0.5 block truncate text-[10px] text-slate-600">Sheet · Row Header · Column Header · Cell Value</span>
      </div>
      {running && (
        <div className="flex items-center gap-2 text-[10px] font-semibold text-violet-700" role="status">
          <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> 셀 검색 문서 생성 중
        </div>
      )}
      {summary && (
        <div className="text-[10px] text-violet-800">
          셀 <strong>{summary.cells}개</strong> · 문서 <strong>{summary.documents}개</strong>
        </div>
      )}
    </NodeShell>
  );
};
