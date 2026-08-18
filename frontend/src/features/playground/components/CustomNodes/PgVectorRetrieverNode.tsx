import type { Node, NodeProps } from '@xyflow/react';
import { Database, Search, CheckCircle2 } from 'lucide-react';
import type { ModuleDefinition } from '../../types';
import { getExecutionNodeState, NodeShell } from '../FlowNode/NodeShell';

interface PgVectorRetrieverNodeData extends Record<string, unknown> {
  executionState?: string;
  executionOutput?: unknown;
  nodeWidth?: number;
  config?: { top_k?: number };
  moduleDefinition?: ModuleDefinition;
  onConfigChange?: (patch: Record<string, unknown>) => void;
  onNodeWidthChange?: (width: number) => void;
}

export type PgVectorRetrieverNodeProps = NodeProps<Node<PgVectorRetrieverNodeData>>;

function getHitCount(output: unknown): number | null {
  if (!output || typeof output !== 'object' || Array.isArray(output)) return null;
  const items = (output as Record<string, unknown>).items;
  return Array.isArray(items) ? items.length : null;
}

export const PgVectorRetrieverNode = ({ data, selected }: PgVectorRetrieverNodeProps) => {
  const topK = data.config?.top_k ?? 100;
  const hitCount = getHitCount(data.executionOutput);

  return (
    <NodeShell
      accent="#0f766e"
      icon={Search}
      eyebrow="🐘 PostgreSQL Logic"
      title="PostgreSQL pgvector Retriever"
      state={getExecutionNodeState(data.executionState)}
      nodeData={data}
      selected={selected}
      width={data.nodeWidth ?? 360}
      onWidthChange={data.onNodeWidthChange}
      inputPorts={['query_input', 'index_input']}
      outputBranches={['dense_result']}
      bodyClassName="space-y-2.5"
    >
      <div className="rounded-lg border border-teal-100 bg-teal-50/70 p-2.5 text-xs text-teal-900 space-y-2">
        <div className="flex items-center justify-between">
          <span className="font-semibold flex items-center gap-1.5">
            <Database className="h-3.5 w-3.5 text-teal-700" /> HNSW 코사인 인덱스 검색
          </span>
          <span className="rounded bg-teal-100 px-1.5 py-0.5 text-[10px] font-bold text-teal-800">
            pgvector 0.8.6
          </span>
        </div>

        <label className="block space-y-1">
          <span className="text-[11px] font-medium text-slate-700">Top-K 후보 개수</span>
          <input
            type="number"
            min={1}
            max={1000}
            className="nodrag nopan w-full rounded border border-teal-200 bg-white px-2 py-1 text-xs text-slate-800 outline-none focus:border-teal-500"
            value={topK}
            onPointerDown={(e) => e.stopPropagation()}
            onChange={(e) =>
              data.onConfigChange?.({ top_k: parseInt(e.currentTarget.value, 10) || 100 })
            }
          />
        </label>
      </div>

      {hitCount !== null && (
        <div className="rounded-lg border border-teal-200 bg-teal-50/40 p-2 text-[10px] flex items-center justify-between text-teal-900 font-semibold">
          <span className="flex items-center gap-1">
            <CheckCircle2 className="h-3 w-3 text-teal-600" /> HNSW 검색 완료
          </span>
          <span>{hitCount}개 후보 검색됨</span>
        </div>
      )}
    </NodeShell>
  );
};
