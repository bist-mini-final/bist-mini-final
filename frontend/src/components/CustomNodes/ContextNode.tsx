import type { Node, NodeProps } from '@xyflow/react';
import { LoaderCircle, Maximize2 } from 'lucide-react';
import { getExecutionNodeState, NodeShell } from '../FlowNode/NodeShell';

interface ContextNodeData extends Record<string, unknown> {
  executionState?: string;
  config?: { top_k?: number; adjacent_radius?: number; max_blocks?: number };
}

export type ContextNodeProps = NodeProps<Node<ContextNodeData>>;

export const ContextNode = ({ data, selected }: ContextNodeProps) => {
  const running = data.executionState === 'running';
  return (
    <NodeShell
      accent="#d97706"
      icon={Maximize2}
      eyebrow="Transform Module"
      title="Context Expander"
      state={getExecutionNodeState(data.executionState)}
      nodeData={data}
      selected={selected}
      width={350}
      inputPorts={['retrieval_json', 'document_input']}
      bodyClassName="space-y-2.5"
    >
      <div className="rounded-xl border border-amber-100 bg-amber-50/70 px-3 py-2.5 text-[10px] text-slate-600">
        RRF Top {data.config?.top_k ?? 100} · 인접 ±{data.config?.adjacent_radius ?? 3}행 · 최대 {data.config?.max_blocks ?? 500}블록
      </div>
      {running && (
        <div className="flex items-center gap-2 text-[10px] font-semibold text-amber-700">
          <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> 실제 셀 컨텍스트 확장 중
        </div>
      )}
    </NodeShell>
  );
};
