import type { Node, NodeProps } from '@xyflow/react';
import { LoaderCircle, Search } from 'lucide-react';
import { getExecutionNodeState, NodeShell } from '../FlowNode/NodeShell';

interface DenseRetrieverNodeData extends Record<string, unknown> {
  executionState?: string;
  executionOutput?: unknown;
  config?: { top_k?: number };
}

function itemCount(output: unknown): number | null {
  if (!output || typeof output !== 'object' || Array.isArray(output)) return null;
  const items = (output as Record<string, unknown>).items;
  return Array.isArray(items) ? items.length : null;
}

export type DenseRetrieverNodeProps = NodeProps<Node<DenseRetrieverNodeData>>;

export const DenseRetrieverNode = ({ data, selected }: DenseRetrieverNodeProps) => {
  const running = data.executionState === 'running';
  const count = itemCount(data.executionOutput);
  return (
    <NodeShell
      accent="#0891b2"
      icon={Search}
      eyebrow="Logic Module"
      title="Dense Vector Retriever"
      state={getExecutionNodeState(data.executionState)}
      nodeData={data}
      selected={selected}
      width={330}
      inputPorts={['query_input', 'index_input']}
      bodyClassName="space-y-2.5"
    >
      <div className="rounded-xl border border-cyan-100 bg-cyan-50/70 px-3 py-2.5 text-[10px] text-slate-600">
        쿼리 벡터·영속 코사인 인덱스 검색 · 쿼리별 Top {data.config?.top_k ?? 1000}
      </div>
      {running && <div className="flex items-center gap-2 text-[10px] font-semibold text-cyan-700"><LoaderCircle className="h-3.5 w-3.5 animate-spin" /> Dense 검색 중</div>}
      {count !== null && <div className="text-[10px] text-cyan-800">후보 <strong>{count}개</strong></div>}
    </NodeShell>
  );
};
