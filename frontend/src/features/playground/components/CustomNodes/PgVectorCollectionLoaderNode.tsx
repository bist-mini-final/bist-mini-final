import { useEffect, useState } from 'react';
import type { Node, NodeProps } from '@xyflow/react';
import { Database, CheckCircle2, RefreshCw, Layers, CheckSquare, Square } from 'lucide-react';
import type { ModuleDefinition } from '../../types';
import { getExecutionNodeState, NodeShell } from '../FlowNode/NodeShell';
import { dataSourceApi } from '../../../data-sources/services/dataSourceApi';

interface PgVectorCollectionLoaderNodeData extends Record<string, unknown> {
  executionState?: string;
  executionOutput?: unknown;
  nodeWidth?: number;
  values?: { collection_name?: string; collection_names?: string[] };
  moduleDefinition?: ModuleDefinition;
  onValuesChange?: (patch: Record<string, unknown>) => void;
  onNodeWidthChange?: (width: number) => void;
}

export type PgVectorCollectionLoaderNodeProps = NodeProps<Node<PgVectorCollectionLoaderNodeData>>;

function getOutputSummary(output: unknown): { docCount: number | null; indexId: string | null } {
  if (!output || typeof output !== 'object' || Array.isArray(output)) {
    return { docCount: null, indexId: null };
  }
  const raw = output as Record<string, unknown>;
  const docOut = raw.document_output as Record<string, unknown> | undefined;
  const idxOut = raw.index_output as Record<string, unknown> | undefined;

  const docCount = Array.isArray(docOut?.items)
    ? docOut.items.length
    : typeof idxOut?.document_count === 'number'
    ? idxOut.document_count
    : null;
  const indexId = typeof idxOut?.index_id === 'string' ? idxOut.index_id : null;

  return { docCount, indexId };
}

export const PgVectorCollectionLoaderNode = ({
  data,
  selected,
}: PgVectorCollectionLoaderNodeProps) => {
  const [availableCollections, setAvailableCollections] = useState<
    Array<{ id: string; name: string; count: number }>
  >([]);
  const [isLoading, setIsLoading] = useState(false);

  const savedIds = Array.isArray(data.values?.collection_names)
    ? (data.values.collection_names as string[]).map((id) => id.trim()).filter(Boolean)
    : typeof data.values?.collection_name === 'string'
      ? data.values.collection_name.split(',').map((id) => id.trim()).filter(Boolean)
      : [];
  const hasSavedValue = savedIds.length > 0;

  // Selected collection IDs (array)
  const selectedIds: string[] = hasSavedValue
    ? savedIds
    : availableCollections.length > 0
    ? [availableCollections[0].id]
    : [];

  useEffect(() => {
    if (!hasSavedValue && availableCollections.length > 0) {
      const defaultId = availableCollections[0].id;
      data.onValuesChange?.({
        collection_names: [defaultId],
        collection_name: defaultId,
      });
    }
  }, [availableCollections, data.onValuesChange, hasSavedValue]);

  const { docCount, indexId } = getOutputSummary(data.executionOutput);

  const fetchCollections = async () => {
    setIsLoading(true);
    try {
      const indexes = await dataSourceApi.listIndexes();
      if (indexes.length > 0) {
        setAvailableCollections(
          indexes.map((idx) => ({
            id: idx.index_id,
            name: idx.file_name || idx.index_id.slice(0, 12),
            count: idx.document_count,
          }))
        );
      }
    } catch {
      // ignore
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchCollections();
  }, []);

  const handleToggleCollection = (id: string) => {
    let next: string[];
    if (selectedIds.includes(id)) {
      next = selectedIds.filter((item) => item !== id);
      if (next.length === 0 && availableCollections.length > 0) {
        next = [id]; // keep at least one
      }
    } else {
      next = [...selectedIds, id];
    }
    data.onValuesChange?.({
      collection_names: next,
      collection_name: next.join(','),
    });
  };

  const handleSelectAll = () => {
    const all = availableCollections.map((c) => c.id);
    data.onValuesChange?.({
      collection_names: all,
      collection_name: all.join(','),
    });
  };

  const totalSelectedVectors = availableCollections
    .filter((c) => selectedIds.includes(c.id))
    .reduce((acc, curr) => acc + curr.count, 0);

  return (
    <NodeShell
      accent="#0f766e"
      icon={Database}
      eyebrow="🐘 PostgreSQL Source"
      title="PostgreSQL pgvector Collection Loader"
      state={getExecutionNodeState(data.executionState)}
      nodeData={data}
      selected={selected}
      width={data.nodeWidth ?? 400}
      onWidthChange={data.onNodeWidthChange}
      hasInput={false}
      hasOutput={true}
      outputBranches={['document_output', 'index_output']}
      bodyClassName="space-y-2.5"
    >
      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <span className="node-field-label">
            <Database className="h-3 w-3 text-teal-700" /> pgvector 컬렉션 다중 선택 ({selectedIds.length}개 선택)
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="text-[10px] text-teal-700 hover:text-teal-900 font-semibold cursor-pointer"
              onClick={handleSelectAll}
              title="전체 컬렉션 선택"
            >
              전체 선택
            </button>
            <button
              type="button"
              className="text-[10px] text-teal-700 hover:text-teal-900 flex items-center gap-0.5 cursor-pointer"
              onClick={fetchCollections}
              title="컬렉션 새로고침"
            >
              <RefreshCw className={`h-2.5 w-2.5 ${isLoading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>

        {availableCollections.length > 0 ? (
          <div className="nodrag nopan max-h-40 overflow-y-auto space-y-1 rounded-lg border border-teal-200 bg-teal-50/50 p-1.5">
            {availableCollections.map((col) => {
              const isChecked = selectedIds.includes(col.id);
              return (
                <button
                  type="button"
                  key={col.id}
                  role="checkbox"
                  aria-checked={isChecked}
                  onClick={() => handleToggleCollection(col.id)}
                  className={`w-full flex items-center justify-between px-2 py-1.5 rounded cursor-pointer text-xs transition-colors ${
                    isChecked
                      ? 'bg-teal-600 text-white font-medium shadow-xs'
                      : 'bg-white text-slate-700 hover:bg-teal-100/70 border border-teal-100'
                  }`}
                >
                  <div className="flex items-center gap-1.5 truncate max-w-[240px]">
                    {isChecked ? (
                      <CheckSquare className="h-3.5 w-3.5 shrink-0" />
                    ) : (
                      <Square className="h-3.5 w-3.5 shrink-0 text-slate-400" />
                    )}
                    <span className="truncate">{col.name}</span>
                  </div>
                  <span className={`text-[10px] shrink-0 font-mono ${isChecked ? 'text-teal-100' : 'text-slate-500'}`}>
                    {col.count.toLocaleString()}개 벡터
                  </span>
                </button>
              );
            })}
          </div>
        ) : (
          <input
            type="text"
            className="nodrag nopan w-full rounded-lg border border-teal-200 bg-teal-50/70 px-2.5 py-2 text-xs font-medium text-slate-800 outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-100"
            value={selectedIds.join(', ')}
            placeholder="SPG_Company_KeyStats_v4.xlsm"
            onPointerDown={(event) => event.stopPropagation()}
            onChange={(event) =>
              data.onValuesChange?.({
                collection_names: event.currentTarget.value.split(',').map((s) => s.trim()).filter(Boolean),
                collection_name: event.currentTarget.value,
              })
            }
          />
        )}

        {availableCollections.length > 0 && (
          <div className="flex items-center justify-between text-[10px] text-teal-800 px-1">
            <span>선택된 벡터 풀:</span>
            <span className="font-bold">{totalSelectedVectors.toLocaleString()}개 벡터</span>
          </div>
        )}
      </div>

      {docCount !== null && (
        <div className="rounded-lg border border-teal-100 bg-teal-50/40 p-2 text-[10px] space-y-1">
          <div className="flex items-center justify-between text-teal-900 font-semibold">
            <span className="flex items-center gap-1">
              <CheckCircle2 className="h-3 w-3 text-teal-600" /> PostgreSQL 연결 완료
            </span>
            <span className="flex items-center gap-1">
              <Layers className="h-3 w-3 text-teal-600" />
              {docCount.toLocaleString()}개 문서 로드됨
            </span>
          </div>
          {indexId && (
            <div className="text-[9px] text-slate-500 font-mono truncate">
              컬렉션 ID: {indexId}
            </div>
          )}
        </div>
      )}
    </NodeShell>
  );
};
