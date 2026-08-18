import type { Node, NodeProps } from '@xyflow/react';
import { LoaderCircle, Route } from 'lucide-react';
import { getExecutionNodeState, NodeShell } from '../FlowNode/NodeShell';

interface SemanticQueryMatcherNodeData extends Record<string, unknown> {
  executionState?: string;
  executionOutput?: unknown;
}

function summary(output: unknown): string | null {
  if (!output || typeof output !== 'object' || Array.isArray(output)) return null;
  const result = (output as Record<string, unknown>).semantic_match;
  if (!result || typeof result !== 'object' || Array.isArray(result)) return null;
  const value = result as Record<string, unknown>;
  if (value.matched !== true) return '전체 인덱스 유지';
  const target = typeof value.target === 'string' ? value.target : '대상';
  const score = typeof value.confidence === 'number' ? ` (${value.confidence.toFixed(3)})` : '';
  return `${target}${score}`;
}

export type SemanticQueryMatcherNodeProps = NodeProps<Node<SemanticQueryMatcherNodeData>>;

export const SemanticQueryMatcherNode = ({ data, selected }: SemanticQueryMatcherNodeProps) => {
  const running = data.executionState === 'running';
  const result = summary(data.executionOutput);
  return (
    <NodeShell
      accent="#7c3aed"
      icon={Route}
      eyebrow="Logic Module"
      title="Semantic Query Matcher"
      state={getExecutionNodeState(data.executionState)}
      selected={selected}
      width={340}
      inputPorts={['query_context']}
      outputBranches={['semantic_match']}
      bodyClassName="space-y-2.5"
    >
      <div className="rounded-xl border border-violet-100 bg-violet-50/70 px-3 py-2.5 text-[10px] text-slate-600">
        예시 질의와 의미적으로 매칭해 대상 시트 범위를 판별합니다.
      </div>
      {running && <div className="flex items-center gap-2 text-[10px] font-semibold text-violet-700"><LoaderCircle className="h-3.5 w-3.5 animate-spin" /> 매칭 중</div>}
      {result && <div className="text-[10px] text-violet-800">↳ <strong>{result}</strong></div>}
    </NodeShell>
  );
};
