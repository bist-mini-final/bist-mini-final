import type { Node, NodeProps } from '@xyflow/react';
import { ArchiveRestore, LoaderCircle } from 'lucide-react';
import { getExecutionNodeState, NodeShell } from '../FlowNode/NodeShell';

interface AnswerCacheWriterNodeData extends Record<string, unknown> {
  executionState?: string;
}

export type AnswerCacheWriterNodeProps = NodeProps<Node<AnswerCacheWriterNodeData>>;

export const AnswerCacheWriterNode = ({ data, selected }: AnswerCacheWriterNodeProps) => {
  const running = data.executionState === 'running';
  return (
    <NodeShell
      accent="#be123c"
      icon={ArchiveRestore}
      eyebrow="Output Module"
      title="Answer Cache Writer"
      state={getExecutionNodeState(data.executionState)}
      selected={selected}
      width={340}
      inputPorts={['question_text', 'answer_json']}
      bodyClassName="space-y-2"
    >
      <p className="m-0 text-[10px] leading-relaxed text-slate-600">
        원문 질문과 Reader 답변을 다음 실행의 Query Input 캐시에 저장합니다.
      </p>
      {running && (
        <div className="flex items-center gap-2 text-[10px] font-semibold text-rose-700">
          <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> 답변 캐시 저장 중
        </div>
      )}
    </NodeShell>
  );
};
