import type { Node, NodeProps } from '@xyflow/react';
import { Database, ScanSearch } from 'lucide-react';
import { getExecutionNodeState, NodeShell } from '../FlowNode/NodeShell';

interface Data extends Record<string, unknown> {
  executionState?: string;
  executionOutput?: unknown;
  nodeWidth?: number;
  onNodeWidthChange?: (width: number) => void;
}

function collectionCount(output: unknown): number | null {
  if (!output || typeof output !== 'object' || Array.isArray(output)) return null;
  const catalog = (output as Record<string, unknown>).scope_catalog;
  if (!catalog || typeof catalog !== 'object' || Array.isArray(catalog)) return null;
  const collections = (catalog as Record<string, unknown>).collections;
  return Array.isArray(collections) ? collections.length : null;
}

export function PgVectorDataScopeNode({ data, selected }: NodeProps<Node<Data>>) {
  const count = collectionCount(data.executionOutput);
  return (
    <NodeShell
      accent="#0f766e"
      icon={Database}
      eyebrow="PostgreSQL Source"
      title="PostgreSQL Data Scope"
      state={getExecutionNodeState(data.executionState)}
      selected={selected}
      width={data.nodeWidth ?? 360}
      nodeData={data}
      onWidthChange={data.onNodeWidthChange}
      hasInput={false}
      hasOutput
      outputBranches={['scope_catalog']}
      bodyClassName="space-y-2.5"
    >
      <div className="flex items-start gap-2 rounded-xl border border-teal-100 bg-teal-50/70 px-3 py-2.5 text-[10px] text-teal-900">
        <ScanSearch className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        <span>collection·company·sheet·embedding 계약만 DB에서 자동 조회합니다. 사용자가 collection을 고르지 않습니다.</span>
      </div>
      {count !== null && (
        <div className="text-[10px] font-semibold text-teal-800">라우팅 가능한 data scope: {count}개</div>
      )}
    </NodeShell>
  );
}
