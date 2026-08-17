import type { Node, NodeProps } from '@xyflow/react';
import { Database, LoaderCircle } from 'lucide-react';
import { getExecutionNodeState, NodeShell } from '../FlowNode/NodeShell';

interface VectorIndexWriterNodeData extends Record<string, unknown> {
  executionState?: string;
  executionOutput?: unknown;
}

function documentCount(output: unknown): number | null {
  if (!output || typeof output !== 'object' || Array.isArray(output)) return null;
  const count = (output as Record<string, unknown>).document_count;
  return typeof count === 'number' ? count : null;
}

export type VectorIndexWriterNodeProps = NodeProps<Node<VectorIndexWriterNodeData>>;

export const VectorIndexWriterNode = ({ data, selected }: VectorIndexWriterNodeProps) => {
  const running = data.executionState === 'running';
  const count = documentCount(data.executionOutput);
  return (
    <NodeShell
      accent="#0f766e"
      icon={Database}
      eyebrow="Transform Module"
      title="Vector Index Writer"
      state={getExecutionNodeState(data.executionState)}
      nodeData={data}
      inputPorts={['input']}
      selected={selected}
      width={350}
      bodyClassName="space-y-2"
    >
      <p className="m-0 text-[10px] leading-relaxed text-slate-600">
        문서 임베딩을 영속 인덱스로 저장하고 index_id만 전달합니다.
      </p>
      {running && (
        <div className="flex items-center gap-2 text-[10px] font-semibold text-teal-700">
          <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> 벡터 인덱스 저장 중
        </div>
      )}
      {count !== null && (
        <div className="text-[10px] text-teal-800">인덱싱 문서 <strong>{count}개</strong></div>
      )}
    </NodeShell>
  );
};
