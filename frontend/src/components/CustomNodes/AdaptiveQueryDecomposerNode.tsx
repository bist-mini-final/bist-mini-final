import type { Node, NodeProps } from '@xyflow/react';
import { GitBranch, LoaderCircle } from 'lucide-react';
import { getExecutionNodeState, NodeShell } from '../FlowNode/NodeShell';

interface AdaptiveQueryDecomposerNodeData extends Record<string, unknown> {
  executionState?: string;
  executionOutput?: unknown;
}

function mode(output: unknown): string | null {
  if (!output || typeof output !== 'object' || Array.isArray(output)) return null;
  const subqueries = (output as Record<string, unknown>).subqueries;
  return Array.isArray(subqueries) ? `${subqueries.length}개 검색 쿼리` : null;
}

export type AdaptiveQueryDecomposerNodeProps = NodeProps<Node<AdaptiveQueryDecomposerNodeData>>;

export const AdaptiveQueryDecomposerNode = ({ data, selected }: AdaptiveQueryDecomposerNodeProps) => {
  const running = data.executionState === 'running';
  const result = mode(data.executionOutput);
  return (
    <NodeShell
      accent="#6d28d9"
      icon={GitBranch}
      eyebrow="Logic Module"
      title="Adaptive Query Decomposer"
      state={getExecutionNodeState(data.executionState)}
      selected={selected}
      width={350}
      inputPorts={['query_context', 'semantic_match']}
      bodyClassName="space-y-2.5"
    >
      <div className="rounded-xl border border-violet-100 bg-violet-50/70 px-3 py-2.5 text-[10px] text-slate-600">
        매칭 성공: 원문 질문으로 바로 검색 · 실패: LLM 서브쿼리 분해
      </div>
      {running && <div className="flex items-center gap-2 text-[10px] font-semibold text-violet-700"><LoaderCircle className="h-3.5 w-3.5 animate-spin" /> 검색 경로 결정 중</div>}
      {result && <div className="text-[10px] text-violet-800">↳ <strong>{result}</strong></div>}
    </NodeShell>
  );
};
