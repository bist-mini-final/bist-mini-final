import { useState } from 'react';
import type { Node, NodeProps } from '@xyflow/react';
import { CloudCog, LoaderCircle } from 'lucide-react';
import { getExecutionNodeState, NodeShell } from '../FlowNode/NodeShell';
import { SpreadsheetInspectAction } from '../SpreadsheetResults/SpreadsheetInspectAction';
import { SpreadsheetResultModal } from '../SpreadsheetResults/SpreadsheetResultModal';


interface LunaVlmStructureDetectorNodeData extends Record<string, unknown> {
  executionState?: string;
  executionInput?: unknown;
  executionOutput?: unknown;
  nodeWidth?: number;
  config?: {
    model?: string;
  };
  onNodeWidthChange?: (width: number) => void;
}

export type LunaVlmStructureDetectorNodeProps = NodeProps<Node<LunaVlmStructureDetectorNodeData>>;

function tableCount(output: unknown): number | null {
  if (!output || typeof output !== 'object' || Array.isArray(output)) return null;
  const tables = (output as Record<string, unknown>).tables;
  return Array.isArray(tables) ? tables.length : null;
}

export const LunaVlmStructureDetectorNode = ({
  data,
  selected,
}: LunaVlmStructureDetectorNodeProps) => {
  const [isInspectorOpen, setIsInspectorOpen] = useState(false);
  const detectedTables = tableCount(data.executionOutput);
  const running = data.executionState === 'running';
  const model = data.config?.model ?? 'gpt-5.6-luna';

  return (
    <>
      <NodeShell
        accent="#4338ca"
        icon={CloudCog}
        eyebrow="Logic Module"
        title="Luna Full-Sheet Structure Detector"
        state={getExecutionNodeState(data.executionState)}
        nodeData={data}
        inputPorts={['input']}
        selected={selected}
        width={data.nodeWidth ?? 390}
        onWidthChange={data.onNodeWidthChange}
        bodyClassName="space-y-2.5"
        headerActions={(
          <SpreadsheetInspectAction
            available={detectedTables !== null}
            label="Luna 전체 시트 구조 식별 결과 보기"
            onInspect={() => setIsInspectorOpen(true)}
          />
        )}
      >
        <div className="rounded-xl border border-indigo-100 bg-indigo-50/70 px-3 py-2.5">
          <span className="block text-[9px] font-bold tracking-[0.12em] text-indigo-700 uppercase">
            Complete Visible Sheet → Single Image → Luna
          </span>
          <span className="mt-0.5 block truncate text-[10px] text-slate-600" title={model}>
            {model} · 시트당 전체 이미지 1회 요청
          </span>
        </div>
        {running && (
          <div className="flex items-center gap-2 rounded-lg border border-indigo-200 bg-white px-2.5 py-2 text-[10px] font-semibold text-indigo-800" role="status">
            <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> 전체 시트 이미지 분석 중
          </div>
        )}
        {detectedTables !== null && (
          <div className="rounded-lg border border-indigo-100 bg-white px-2.5 py-2 text-[10px] text-indigo-800">
            식별된 테이블 <strong>{detectedTables}개</strong>
          </div>
        )}
      </NodeShell>
      {isInspectorOpen && (
        <SpreadsheetResultModal
          kind="luna_vlm"
          input={data.executionInput}
          output={data.executionOutput}
          onClose={() => setIsInspectorOpen(false)}
        />
      )}
    </>
  );
};
