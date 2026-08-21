import type { Node, NodeProps } from '@xyflow/react';
import { ArrowRight } from 'lucide-react';
import { getExecutionNodeState, NodeShell } from '../FlowNode/NodeShell';

interface DirectQueryDecomposerNodeData extends Record<string, unknown> {
  executionState?: string;
}

export const DirectQueryDecomposerNode = ({ data, selected }: NodeProps<Node<DirectQueryDecomposerNodeData>>) => (
  <NodeShell
    accent="#475569"
    icon={ArrowRight}
    eyebrow="Baseline Module"
    title="Direct Query Baseline"
    state={getExecutionNodeState(data.executionState)}
    selected={selected}
    width={320}
    nodeData={data}
    inputPorts={['query_context']}
  >
    <p className="m-0 text-[11px] leading-relaxed text-slate-600">
      LLM 호출 없이 질문을 하나의 검색 쿼리로 사용합니다.
    </p>
  </NodeShell>
);
