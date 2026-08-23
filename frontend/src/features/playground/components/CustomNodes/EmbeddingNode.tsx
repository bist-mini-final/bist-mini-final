import type { Node, NodeProps } from '@xyflow/react';
import { Cpu } from 'lucide-react';
import { getExecutionNodeState, NodeShell } from '../FlowNode/NodeShell';

interface EmbeddingNodeData extends Record<string, unknown> {
  activeStep: number;
  executionState?: string;
}

export type EmbeddingNodeProps = NodeProps<Node<EmbeddingNodeData>>;

export const EmbeddingNode = ({ data, selected }: EmbeddingNodeProps) => {
  return (
    <NodeShell
      accent="#0891b2"
      icon={Cpu}
      eyebrow="Logic Module"
      title="Query Embedder"
      state={getExecutionNodeState(data.executionState)}
      nodeData={data}
      inputPorts={['retrieval_plan']}
      selected={selected}
      width={320}
      bodyClassName="space-y-2"
    >
      <div className="rounded-xl border border-cyan-100 bg-cyan-50/70 px-3 py-2.5">
        <span className="block text-[9px] font-bold tracking-[0.12em] text-cyan-700 uppercase">
          Embedding Contract
        </span>
        <code
          className="mt-1 block truncate text-[11px] font-semibold text-slate-700"
          title="선택한 인덱스의 모델과 차원을 사용합니다"
        >
          INDEX MODEL · DIMENSION
        </code>
      </div>
    </NodeShell>
  );
};
