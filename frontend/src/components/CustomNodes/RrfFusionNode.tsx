import type { Node, NodeProps } from '@xyflow/react';
import { LoaderCircle, Merge } from 'lucide-react';
import { getExecutionNodeState, NodeShell } from '../FlowNode/NodeShell';

interface RrfFusionNodeData extends Record<string, unknown> {
  executionState?: string;
  executionOutput?: unknown;
  config?: { rrf_k?: number; top_k?: number; ratio_penalty?: number };
}

function itemCount(output: unknown): number | null {
  if (!output || typeof output !== 'object' || Array.isArray(output)) return null;
  const items = (output as Record<string, unknown>).items;
  return Array.isArray(items) ? items.length : null;
}

export type RrfFusionNodeProps = NodeProps<Node<RrfFusionNodeData>>;

export const RrfFusionNode = ({ data, selected }: RrfFusionNodeProps) => {
  const running = data.executionState === 'running';
  const count = itemCount(data.executionOutput);
  return (
    <NodeShell
      accent="#059669"
      icon={Merge}
      eyebrow="Logic Module"
      title="RRF Fusion"
      state={getExecutionNodeState(data.executionState)}
      selected={selected}
      width={350}
      inputPorts={['bm25_result', 'dense_result']}
      bodyClassName="space-y-2.5"
    >
      <div className="rounded-xl border border-emerald-100 bg-emerald-50/70 px-3 py-2.5 text-[10px] text-slate-600">
        RRF k={data.config?.rrf_k ?? 60} · Top {data.config?.top_k ?? 100} · Ratio ×{data.config?.ratio_penalty ?? 0.4}
      </div>
      {running && <div className="flex items-center gap-2 text-[10px] font-semibold text-emerald-700"><LoaderCircle className="h-3.5 w-3.5 animate-spin" /> 두 검색 순위 결합 중</div>}
      {count !== null && <div className="text-[10px] text-emerald-800">결합 후보 <strong>{count}개</strong></div>}
    </NodeShell>
  );
};
