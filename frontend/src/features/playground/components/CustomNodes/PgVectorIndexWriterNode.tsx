import type { Node, NodeProps } from '@xyflow/react';
import { Database, CheckCircle2, Server } from 'lucide-react';
import type { ModuleDefinition } from '../../types';
import { getExecutionNodeState, NodeShell } from '../FlowNode/NodeShell';

interface PgVectorIndexWriterNodeData extends Record<string, unknown> {
  executionState?: string;
  executionOutput?: unknown;
  nodeWidth?: number;
  moduleDefinition?: ModuleDefinition;
  onNodeWidthChange?: (width: number) => void;
}

export type PgVectorIndexWriterNodeProps = NodeProps<Node<PgVectorIndexWriterNodeData>>;

function getWriterSummary(output: unknown): {
  indexId: string | null;
  docCount: number | null;
  model: string | null;
} {
  if (!output || typeof output !== 'object' || Array.isArray(output)) {
    return { indexId: null, docCount: null, model: null };
  }
  const raw = output as Record<string, unknown>;
  const indexId = typeof raw.index_id === 'string' ? raw.index_id : null;
  const docCount = typeof raw.document_count === 'number' ? raw.document_count : null;
  const model = typeof raw.model === 'string' ? raw.model : null;

  return { indexId, docCount, model };
}

export const PgVectorIndexWriterNode = ({ data, selected }: PgVectorIndexWriterNodeProps) => {
  const { indexId, docCount, model } = getWriterSummary(data.executionOutput);

  return (
    <NodeShell
      accent="#0f766e"
      icon={Database}
      eyebrow="🐘 PostgreSQL Storage"
      title="PostgreSQL pgvector Writer"
      state={getExecutionNodeState(data.executionState)}
      nodeData={data}
      selected={selected}
      width={data.nodeWidth ?? 360}
      onWidthChange={data.onNodeWidthChange}
      inputPorts={['input']}
      outputBranches={['index_output']}
      bodyClassName="space-y-2.5"
    >
      <div className="rounded-lg border border-teal-100 bg-teal-50/70 p-2.5 text-xs text-teal-900 space-y-1.5">
        <div className="flex items-center justify-between font-semibold">
          <span className="flex items-center gap-1">
            <Server className="h-3.5 w-3.5 text-teal-700" /> PostgreSQL 16
          </span>
          <span className="text-[10px] text-teal-700 font-mono">PGVECTOR_URL 환경변수</span>
        </div>
        <div className="text-[10px] text-slate-600 leading-snug">
          6개 ERD 테이블(<code>source_files</code>, <code>sheets</code>, <code>document_chunks</code>, <code>vector_indexes</code>, <code>langchain_pg_collection</code>, <code>langchain_pg_embedding</code>)에 IVFFlat 코사인 벡터를 영구 적재합니다.
        </div>
      </div>

      {docCount !== null && (
        <div className="rounded-lg border border-teal-200 bg-teal-50/40 p-2 text-[10px] space-y-1">
          <div className="flex items-center justify-between text-teal-900 font-semibold">
            <span className="flex items-center gap-1">
              <CheckCircle2 className="h-3 w-3 text-teal-600" /> pgvector 적재 완료
            </span>
            <span className="font-bold text-teal-800">{docCount.toLocaleString()}개 청크</span>
          </div>
          {model && (
            <div className="text-[9px] text-slate-500 font-mono">
              모델: {model} · IVFFlat Cosine Index
            </div>
          )}
          {indexId && (
            <div className="text-[9px] text-slate-400 font-mono truncate">
              컬렉션 ID: {indexId}
            </div>
          )}
        </div>
      )}
    </NodeShell>
  );
};
