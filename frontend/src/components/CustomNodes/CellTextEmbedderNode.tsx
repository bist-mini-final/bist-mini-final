import type { Node, NodeProps } from '@xyflow/react';
import { Binary, LoaderCircle } from 'lucide-react';
import { getExecutionNodeState, NodeShell } from '../FlowNode/NodeShell';

interface CellTextEmbedderNodeData extends Record<string, unknown> {
  executionState?: string;
  executionOutput?: unknown;
  config?: { model?: string; batch_size?: number };
}

function itemCount(output: unknown): number | null {
  if (!output || typeof output !== 'object' || Array.isArray(output)) return null;
  const items = (output as Record<string, unknown>).items;
  return Array.isArray(items) ? items.length : null;
}

export type CellTextEmbedderNodeProps = NodeProps<Node<CellTextEmbedderNodeData>>;

export const CellTextEmbedderNode = ({ data, selected }: CellTextEmbedderNodeProps) => {
  const running = data.executionState === 'running';
  const count = itemCount(data.executionOutput);

  return (
    <NodeShell
      accent="#0f766e"
      icon={Binary}
      eyebrow="Logic Module"
      title="BGE Cell Text Embedder"
      state={getExecutionNodeState(data.executionState)}
      nodeData={data}
      selected={selected}
      width={340}
      bodyClassName="space-y-2.5"
    >
      <div className="rounded-xl border border-teal-100 bg-teal-50/70 px-3 py-2.5 text-[10px] text-slate-600">
        <span className="block truncate" title={data.config?.model ?? 'BAAI/bge-large-en-v1.5'}>
          {data.config?.model ?? 'BAAI/bge-large-en-v1.5'}
        </span>
        <span className="block">Batch {data.config?.batch_size ?? 64}</span>
      </div>
      {running && (
        <div className="flex items-center gap-2 text-[10px] font-semibold text-teal-700">
          <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> 문서 임베딩 중
        </div>
      )}
      {count !== null && (
        <div className="text-[10px] text-teal-800">임베딩 문서 <strong>{count}개</strong></div>
      )}
    </NodeShell>
  );
};
