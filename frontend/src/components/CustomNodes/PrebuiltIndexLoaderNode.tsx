import { useEffect } from 'react';
import type { Node, NodeProps } from '@xyflow/react';
import { FolderArchive, FolderOpen, CheckCircle2 } from 'lucide-react';
import type { ModuleDefinition } from '../../types';
import { getExecutionNodeState, NodeShell } from '../FlowNode/NodeShell';

interface PrebuiltIndexLoaderNodeData extends Record<string, unknown> {
  executionState?: string;
  executionOutput?: unknown;
  nodeWidth?: number;
  config?: { file_name?: string };
  moduleDefinition?: ModuleDefinition;
  onConfigChange?: (patch: Record<string, unknown>) => void;
  onNodeWidthChange?: (width: number) => void;
}

export type PrebuiltIndexLoaderNodeProps = NodeProps<Node<PrebuiltIndexLoaderNodeData>>;

function getOutputSummary(output: unknown): { docCount: number | null; indexId: string | null } {
  if (!output || typeof output !== 'object' || Array.isArray(output)) {
    return { docCount: null, indexId: null };
  }
  const raw = output as Record<string, unknown>;
  const docOut = raw.document_output as Record<string, unknown> | undefined;
  const idxOut = raw.index_output as Record<string, unknown> | undefined;

  const docCount = Array.isArray(docOut?.items) ? docOut.items.length : null;
  const indexId = typeof idxOut?.index_id === 'string' ? idxOut.index_id : null;

  return { docCount, indexId };
}

export const PrebuiltIndexLoaderNode = ({ data, selected }: PrebuiltIndexLoaderNodeProps) => {
  const fileSchema = data.moduleDefinition?.config_schema.properties?.file_name;
  const fileOptions = (fileSchema?.enum ?? []).filter(
    (candidate): candidate is string => typeof candidate === 'string'
  );
  const schemaDefault = typeof fileSchema?.default === 'string'
    ? fileSchema.default
    : 'SPG_Company_KeyStats_v3_prebuilt.parquet';

  const selectedFile = data.config?.file_name || schemaDefault;
  const { docCount, indexId } = getOutputSummary(data.executionOutput);

  useEffect(() => {
    if (!data.config?.file_name && selectedFile) {
      data.onConfigChange?.({ file_name: selectedFile });
    }
  }, [data.config?.file_name, data.onConfigChange, selectedFile]);

  return (
    <NodeShell
      accent="#059669"
      icon={FolderArchive}
      eyebrow="Source Module"
      title="Pre-built Vector Index Loader"
      state={getExecutionNodeState(data.executionState)}
      nodeData={data}
      selected={selected}
      width={data.nodeWidth ?? 360}
      onWidthChange={data.onNodeWidthChange}
      hasInput={false}
      hasOutput={true}
      outputBranches={['document_output', 'index_output']}
      bodyClassName="space-y-2.5"
    >
      <label className="block space-y-1.5">
        <span className="node-field-label">
          <FolderOpen className="h-3 w-3 text-emerald-700" /> 사전 구축 인덱스 파일 (.parquet / .json)
        </span>
        {fileOptions.length > 0 ? (
          <select
            className="nodrag nopan w-full cursor-pointer rounded-lg border border-emerald-200 bg-emerald-50/70 px-2.5 py-2 text-xs font-medium text-slate-800 outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
            value={selectedFile}
            onPointerDown={(event) => event.stopPropagation()}
            onChange={(event) => data.onConfigChange?.({ file_name: event.currentTarget.value })}
            aria-label="사전 구축 인덱스 파일 선택"
          >
            {fileOptions.map((fileName) => (
              <option key={fileName} value={fileName}>{fileName}</option>
            ))}
          </select>
        ) : (
          <input
            type="text"
            className="nodrag nopan w-full rounded-lg border border-emerald-200 bg-emerald-50/70 px-2.5 py-2 text-xs font-medium text-slate-800 outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
            value={selectedFile}
            placeholder="SPG_Company_KeyStats_v3_prebuilt.parquet"
            onPointerDown={(event) => event.stopPropagation()}
            onChange={(event) => data.onConfigChange?.({ file_name: event.currentTarget.value })}
          />
        )}
      </label>

      {docCount !== null && (
        <div className="rounded-lg border border-emerald-100 bg-emerald-50/40 p-2 text-[10px] space-y-1">
          <div className="flex items-center justify-between text-emerald-900 font-semibold">
            <span className="flex items-center gap-1"><CheckCircle2 className="h-3 w-3 text-emerald-600" /> 로드 완료</span>
            <span>{docCount}개 셀 문서</span>
          </div>
          {indexId && (
            <div className="truncate font-mono text-[9px] text-slate-500" title={indexId}>
              Index: {indexId}
            </div>
          )}
        </div>
      )}
    </NodeShell>
  );
};
