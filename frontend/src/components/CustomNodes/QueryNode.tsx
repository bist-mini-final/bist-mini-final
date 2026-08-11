import { useEffect, useRef, useState } from 'react';
import type { Node, NodeProps } from '@xyflow/react';
import { MessageSquare } from 'lucide-react';
import { getExecutionNodeState, NodeShell } from '../FlowNode/NodeShell';

interface QueryNodeData extends Record<string, unknown> {
  queryText: string;
  setQueryText: (text: string) => void;
  activeStep: number;
  executionState?: string;
  outputBranches?: string[];
}

export type QueryNodeProps = NodeProps<Node<QueryNodeData>>;

export const QueryNode = ({ data, selected }: QueryNodeProps) => {
  const { queryText, setQueryText } = data;
  const [draftQuery, setDraftQuery] = useState(queryText);
  const isComposing = useRef(false);

  useEffect(() => {
    if (!isComposing.current) setDraftQuery(queryText);
  }, [queryText]);

  const commitQuery = (value: string) => {
    setDraftQuery(value);
    setQueryText(value);
  };

  return (
    <NodeShell
      accent="#107c41"
      icon={MessageSquare}
      eyebrow="Source Module"
      title="사용자 질의 (Query Input)"
      state={getExecutionNodeState(data.executionState)}
      selected={selected}
      hasInput={false}
      outputBranches={data.outputBranches}
      bodyClassName="space-y-3"
    >
        <div className="space-y-2">
          <label className="node-field-label">
            자연어 재무 질문 입력
          </label>
          <textarea
            value={draftQuery}
            onCompositionStart={() => {
              isComposing.current = true;
            }}
            onCompositionEnd={(e) => {
              isComposing.current = false;
              commitQuery(e.currentTarget.value);
            }}
            onChange={(e) => {
              const value = e.currentTarget.value;
              const nativeEvent = e.nativeEvent as InputEvent;
              setDraftQuery(value);
              if (!isComposing.current && !nativeEvent.isComposing) {
                setQueryText(value);
              }
            }}
            placeholder="실험할 질문을 자유롭게 입력하세요..."
            className="nodrag nopan nowheel w-full h-22 px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl text-slate-800 placeholder-slate-400 focus:outline-none focus:border-[#107c41] focus:bg-white focus:ring-2 focus:ring-emerald-100 transition-all resize-none leading-relaxed"
          />
          <p className="m-0 text-[10px] text-slate-500">
            다음 배치 또는 자동 실행 시 이 질문이 입력으로 전달됩니다.
          </p>
        </div>
    </NodeShell>
  );
};
