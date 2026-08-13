import { useState } from 'react';
import type { Node, NodeProps } from '@xyflow/react';
import { LoaderCircle, TableProperties } from 'lucide-react';
import { getExecutionNodeState, NodeShell } from '../FlowNode/NodeShell';
import { SpreadsheetInspectAction } from '../SpreadsheetResults/SpreadsheetInspectAction';
import { SpreadsheetResultModal } from '../SpreadsheetResults/SpreadsheetResultModal';


interface OpenpyxlRegionDetectorNodeData extends Record<string, unknown> {
  executionState?: string;
  executionInput?: unknown;
  executionOutput?: unknown;
  nodeWidth?: number;
  config?: {
    header_scan_rows?: number;
    bold_ratio_threshold?: number;
    fill_ratio_threshold?: number;
  };
  onNodeWidthChange?: (width: number) => void;
}

export type OpenpyxlRegionDetectorNodeProps = NodeProps<Node<OpenpyxlRegionDetectorNodeData>>;

function regionCount(output: unknown): number | null {
  if (!output || typeof output !== 'object' || Array.isArray(output)) return null;
  const tables = (output as Record<string, unknown>).tables;
  if (!Array.isArray(tables)) return null;
  return tables.reduce((total, table) => {
    if (!table || typeof table !== 'object' || Array.isArray(table)) return total;
    const regions = (table as Record<string, unknown>).regions;
    return total + (Array.isArray(regions) ? regions.length : 0);
  }, 0);
}

export const OpenpyxlRegionDetectorNode = ({ data, selected }: OpenpyxlRegionDetectorNodeProps) => {
  const [isInspectorOpen, setIsInspectorOpen] = useState(false);
  const detectedRegions = regionCount(data.executionOutput);
  const running = data.executionState === 'running';

  return (
    <>
      <NodeShell
        accent="#d97706"
        icon={TableProperties}
        eyebrow="Logic Module"
        title="OpenPyXL Table Region Classifier"
        state={getExecutionNodeState(data.executionState)}
      nodeData={data}
        selected={selected}
        width={data.nodeWidth ?? 350}
        onWidthChange={data.onNodeWidthChange}
        bodyClassName="space-y-2.5"
        headerActions={(
          <SpreadsheetInspectAction
            available={detectedRegions !== null}
            label="OpenPyXL 분류 결과 보기"
            onInspect={() => setIsInspectorOpen(true)}
          />
        )}
      >
        <div className="rounded-xl border border-amber-100 bg-amber-50/70 px-3 py-2.5">
          <span className="block text-[9px] font-bold tracking-[0.12em] text-amber-700 uppercase">Formatting Heuristic</span>
          <span className="mt-0.5 block text-[10px] text-slate-600">column header · row header · data</span>
        </div>
        {running && (
          <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-white px-2.5 py-2 text-[10px] font-semibold text-amber-800" role="status">
            <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> 셀 서식 기반 영역 분류 중
          </div>
        )}
        {detectedRegions !== null && (
          <div className="rounded-lg border border-amber-100 bg-white px-2.5 py-2 text-[10px] text-amber-800">
            분류 영역 <strong>{detectedRegions}개</strong>
          </div>
        )}
      </NodeShell>
      {isInspectorOpen && (
        <SpreadsheetResultModal
          kind="openpyxl"
          input={data.executionInput}
          output={data.executionOutput}
          onClose={() => setIsInspectorOpen(false)}
        />
      )}
    </>
  );
};
