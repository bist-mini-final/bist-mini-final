import type { Node, NodeProps } from '@xyflow/react';
import { LoaderCircle, SearchCheck } from 'lucide-react';
import { getExecutionNodeState, NodeShell } from '../FlowNode/NodeShell';

interface SemanticScopedDenseRetrieverNodeData extends Record<string, unknown> {
  executionState?: string;
  executionOutput?: unknown;
  config?: { top_k?: number };
}

function itemCount(output: unknown): number | null {
  if (!output || typeof output !== 'object' || Array.isArray(output)) return null;
  const items = (output as Record<string, unknown>).items;
  return Array.isArray(items) ? items.length : null;
}

export type SemanticScopedDenseRetrieverNodeProps = NodeProps<Node<SemanticScopedDenseRetrieverNodeData>>;

export const SemanticScopedDenseRetrieverNode = ({ data, selected }: SemanticScopedDenseRetrieverNodeProps) => {
  const running = data.executionState === 'running';
  const count = itemCount(data.executionOutput);
  return (
    <NodeShell
      accent="#0f766e"
      icon={SearchCheck}
      eyebrow="Logic Module"
      title="Semantic-Scoped Dense Retriever"
      state={getExecutionNodeState(data.executionState)}
      selected={selected}
      width={360}
      inputPorts={['query_input', 'index_input', 'semantic_match']}
      bodyClassName="space-y-2.5"
    >
      <div className="rounded-xl border border-teal-100 bg-teal-50/70 px-3 py-2.5 text-[10px] text-slate-600">
        매칭 시트 범위에서 Dense 검색 · 불확실하면 전체 검색 · Top {data.config?.top_k ?? 1000}
      </div>
      {running && <div className="flex items-center gap-2 text-[10px] font-semibold text-teal-700"><LoaderCircle className="h-3.5 w-3.5 animate-spin" /> Dense 검색 중</div>}
      {count !== null && <div className="text-[10px] text-teal-800">후보 <strong>{count}개</strong></div>}
    </NodeShell>
  );
};
