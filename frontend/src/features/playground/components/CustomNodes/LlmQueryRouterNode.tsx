import type { Node, NodeProps } from '@xyflow/react';
import { Bot, LoaderCircle } from 'lucide-react';
import { getExecutionNodeState, NodeShell } from '../FlowNode/NodeShell';

interface Data extends Record<string, unknown> { executionState?: string; executionOutput?: unknown }

export function LlmQueryRouterNode({ data, selected }: NodeProps<Node<Data>>) {
  const output = data.executionOutput as { semantic_match?: { target?: string | null; matched?: boolean } } | undefined;
  const route = output?.semantic_match?.matched ? output.semantic_match.target : '전체 인덱스 폴백';
  return <NodeShell accent="#c026d3" icon={Bot} eyebrow="Logic Module" title="LLM Query Router"
    state={getExecutionNodeState(data.executionState)} selected={selected} width={340}
    inputPorts={['query_context']} outputBranches={['semantic_match']} bodyClassName="space-y-2.5">
    <div className="rounded-xl border border-fuchsia-100 bg-fuchsia-50/70 px-3 py-2.5 text-[10px] text-slate-600">LLM이 source/sheet를 선택합니다. 시맨틱 라우터와 교체해 A/B 비교합니다.</div>
    {data.executionState === 'running' && <div className="flex items-center gap-2 text-[10px] font-semibold text-fuchsia-700"><LoaderCircle className="h-3.5 w-3.5 animate-spin" /> 라우팅 중</div>}
    {data.executionState === 'succeeded' && <div className="text-[10px] text-fuchsia-800">경로: <strong>{route}</strong></div>}
  </NodeShell>;
}
