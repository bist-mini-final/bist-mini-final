import { useEffect } from 'react';
import type { Node, NodeProps } from '@xyflow/react';
import { FileSpreadsheet, FolderOpen } from 'lucide-react';
import type { ModuleDefinition } from '../../types';
import { getExecutionNodeState, NodeShell } from '../FlowNode/NodeShell';


interface ProcessedFileSelectorNodeData extends Record<string, unknown> {
  executionState?: string;
  executionOutput?: unknown;
  nodeWidth?: number;
  config?: { file_name?: string };
  moduleDefinition?: ModuleDefinition;
  onConfigChange?: (patch: Record<string, unknown>) => void;
  onNodeWidthChange?: (width: number) => void;
}

export type ProcessedFileSelectorNodeProps = NodeProps<Node<ProcessedFileSelectorNodeData>>;

function selectedSheetCount(output: unknown): number | null {
  if (!output || typeof output !== 'object' || Array.isArray(output)) return null;
  const sheetNames = (output as Record<string, unknown>).sheet_names;
  return Array.isArray(sheetNames) ? sheetNames.length : null;
}

export const ProcessedFileSelectorNode = ({ data, selected }: ProcessedFileSelectorNodeProps) => {
  const fileSchema = data.moduleDefinition?.config_schema.properties?.file_name;
  const fileOptions = (fileSchema?.enum ?? []).filter(
    (candidate): candidate is string => typeof candidate === 'string'
  );
  const schemaDefault = typeof fileSchema?.default === 'string' ? fileSchema.default : '';
  const selectedFile = data.config?.file_name || schemaDefault || fileOptions[0] || '';
  const sheetCount = selectedSheetCount(data.executionOutput);

  useEffect(() => {
    if (!data.config?.file_name && selectedFile) {
      data.onConfigChange?.({ file_name: selectedFile });
    }
  }, [data.config?.file_name, data.onConfigChange, selectedFile]);

  return (
    <NodeShell
      accent="#107c41"
      icon={FileSpreadsheet}
      eyebrow="Source Module"
      title="Processed Excel File Selector"
      state={getExecutionNodeState(data.executionState)}
      selected={selected}
      width={data.nodeWidth ?? 340}
      onWidthChange={data.onNodeWidthChange}
      hasInput={false}
      bodyClassName="space-y-2.5"
    >
      <label className="block space-y-1.5">
        <span className="node-field-label">
          <FolderOpen className="h-3 w-3 text-emerald-700" /> processed 파일
        </span>
        <select
          className="nodrag nopan w-full cursor-pointer rounded-lg border border-emerald-200 bg-emerald-50/70 px-2.5 py-2 text-xs font-medium text-slate-800 outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
          value={selectedFile}
          disabled={fileOptions.length === 0}
          onPointerDown={(event) => event.stopPropagation()}
          onChange={(event) => data.onConfigChange?.({ file_name: event.currentTarget.value })}
          aria-label="processed Excel 파일 선택"
        >
          {fileOptions.length === 0 && <option value="">선택 가능한 Excel 파일 없음</option>}
          {fileOptions.map((fileName) => (
            <option key={fileName} value={fileName}>{fileName}</option>
          ))}
        </select>
      </label>
      {sheetCount !== null && (
        <div className="rounded-lg border border-emerald-100 bg-white px-2.5 py-2 text-[10px] text-emerald-800">
          내부·빈 시트를 제외한 처리 대상 <strong>{sheetCount}개</strong>
        </div>
      )}
    </NodeShell>
  );
};

