import type { Node, NodeProps } from '@xyflow/react';
import { Bot, GitBranch, LoaderCircle } from 'lucide-react';
import { getExecutionNodeState, NodeShell } from '../FlowNode/NodeShell';

const MODEL_OPTIONS = [
  { value: 'gpt-5.6-luna', label: 'GPT-5.6 Luna · 효율 중심' },
  { value: 'gpt-5.6-terra', label: 'GPT-5.6 Terra · 균형' },
  { value: 'gpt-5.6-sol', label: 'GPT-5.6 Sol · 품질 중심' },
];

interface DecomposerNodeData extends Record<string, unknown> {
  activeStep: number;
  executionState?: string;
  config?: {
    model?: string;
  };
  onConfigChange?: (patch: Record<string, unknown>) => void;
}

export type DecomposerNodeProps = NodeProps<Node<DecomposerNodeData>>;

export const DecomposerNode = ({ id, data, selected }: DecomposerNodeProps) => {
  const isWaitingForResponse = data.executionState === 'running';
  const selectedModel = data.config?.model ?? 'gpt-5.6-luna';
  const modelOptions = MODEL_OPTIONS.some((option) => option.value === selectedModel)
    ? MODEL_OPTIONS
    : [{ value: selectedModel, label: `${selectedModel} · 설정값` }, ...MODEL_OPTIONS];

  return (
    <NodeShell
      accent="#7c3aed"
      icon={GitBranch}
      eyebrow="Logic Module"
      title="Scope-aware Query Decomposer"
      state={getExecutionNodeState(data.executionState)}
      selected={selected}
      width={360}
      nodeData={data}
      inputPorts={['query_context', 'scope_catalog']}
      outputBranches={['retrieval_plan']}
      bodyClassName="space-y-3"
    >
      <div className="space-y-1.5">
        <label className="node-field-label" htmlFor={`decomposer-model-${id}`}>
          <Bot className="h-3 w-3 text-violet-600" /> 범위 지정·질의 분해 LLM 모델
        </label>
        <select
          id={`decomposer-model-${id}`}
          className="nodrag nopan w-full cursor-pointer rounded-lg border border-violet-200 bg-violet-50/60 px-2.5 py-1.5 text-xs font-medium text-violet-950 outline-none transition-colors focus:border-violet-500 focus:ring-2 focus:ring-violet-100 disabled:cursor-wait disabled:opacity-60"
          value={selectedModel}
          disabled={isWaitingForResponse}
          onPointerDown={(event) => event.stopPropagation()}
          onChange={(event) => data.onConfigChange?.({ model: event.currentTarget.value })}
          aria-label="질의 분해 LLM 모델 선택"
        >
          {modelOptions.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
        <p className="m-0 text-[10px] text-slate-500">
          모델을 변경하면 해당 모델 조합의 별도 캐시를 사용합니다.
        </p>
      </div>

      {isWaitingForResponse && (
        <div
          className="flex items-start gap-2.5 rounded-xl border border-violet-200 bg-violet-50/80 p-3 text-violet-900"
          role="status"
          aria-live="polite"
        >
          <LoaderCircle className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-violet-600" />
          <div className="min-w-0">
            <p className="m-0 text-[11px] font-bold">검색 계획 생성 요청 전송됨</p>
            <p className="mt-1 mb-0 text-[10px] leading-relaxed text-violet-700">
              DB catalog 안에서 기업·시트별 서브쿼리를 생성하고 있습니다.
            </p>
          </div>
        </div>
      )}
    </NodeShell>
  );
};
