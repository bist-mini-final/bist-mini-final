import type { Node, NodeProps } from '@xyflow/react';
import { Bot, LoaderCircle } from 'lucide-react';
import { getExecutionNodeState, NodeShell } from '../FlowNode/NodeShell';

interface Data extends Record<string, unknown> { executionState?: string; executionOutput?: unknown }

export function LlmQueryRouterNode({ data, selected }: NodeProps<Node<Data>>) {
  const output = data.executionOutput as { routes?: unknown[] } | undefined;
  const routeCount = Array.isArray(output?.routes) ? output.routes.length : null;
  return <NodeShell accent="#c026d3" icon={Bot} eyebrow="Logic Module" title="LLM Query Router"
    state={getExecutionNodeState(data.executionState)} selected={selected} width={340}
    inputPorts={['query_input', 'scope_catalog']} outputBranches={['retrieval_plan']} bodyClassName="space-y-2.5">
    <div className="rounded-xl border border-fuchsia-100 bg-fuchsia-50/70 px-3 py-2.5 text-[10px] text-slate-600">각 서브쿼리를 DB catalog의 concrete collection에 자동 대응합니다.</div>
    {data.executionState === 'running' && <div className="flex items-center gap-2 text-[10px] font-semibold text-fuchsia-700"><LoaderCircle className="h-3.5 w-3.5 animate-spin" /> 라우팅 중</div>}
    {data.executionState === 'succeeded' && routeCount !== null && <div className="text-[10px] text-fuchsia-800">서브쿼리별 경로: <strong>{routeCount}개</strong></div>}
  </NodeShell>;
}
