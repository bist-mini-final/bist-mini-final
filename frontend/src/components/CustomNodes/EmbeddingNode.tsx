import type { Node, NodeProps } from '@xyflow/react';
import { Cpu } from 'lucide-react';
import { getExecutionNodeState, NodeShell } from '../FlowNode/NodeShell';

interface EmbeddingNodeData extends Record<string, unknown> {
  activeStep: number;
  executionState?: string;
  config?: {
    model?: string;
  };
}

export type EmbeddingNodeProps = NodeProps<Node<EmbeddingNodeData>>;

const DEFAULT_EMBEDDING_MODEL = 'BAAI/bge-large-en-v1.5';

export const EmbeddingNode = ({ data, selected }: EmbeddingNodeProps) => {
  const model = data.config?.model?.trim() || DEFAULT_EMBEDDING_MODEL;

  return (
    <NodeShell
      accent="#0891b2"
      icon={Cpu}
      eyebrow="Logic Module"
      title="Query Embedder"
      state={getExecutionNodeState(data.executionState)}
      nodeData={data}
      selected={selected}
      width={320}
      bodyClassName="space-y-2"
    >
      <div className="rounded-xl border border-cyan-100 bg-cyan-50/70 px-3 py-2.5">
        <span className="block text-[9px] font-bold tracking-[0.12em] text-cyan-700 uppercase">
          Embedding Model
        </span>
        <code
          className="mt-1 block truncate text-[11px] font-semibold text-slate-700"
          title={model}
        >
          {model}
        </code>
      </div>
    </NodeShell>
  );
};
