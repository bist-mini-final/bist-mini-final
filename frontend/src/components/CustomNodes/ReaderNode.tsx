import type { Node, NodeProps } from '@xyflow/react';
import { Bot, LoaderCircle, Sparkles } from 'lucide-react';
import { getExecutionNodeState, NodeShell } from '../FlowNode/NodeShell';

const MODEL_OPTIONS = [
  { value: 'gpt-5.6-luna', label: 'GPT-5.6 Luna · 효율 중심' },
  { value: 'gpt-5.6-terra', label: 'GPT-5.6 Terra · 균형' },
  { value: 'gpt-5.6-sol', label: 'GPT-5.6 Sol · 품질 중심' },
];

interface ReaderNodeData extends Record<string, unknown> {
  executionState?: string;
  config?: { model?: string };
  onConfigChange?: (patch: Record<string, unknown>) => void;
}

export type ReaderNodeProps = NodeProps<Node<ReaderNodeData>>;

export const ReaderNode = ({ id, data, selected }: ReaderNodeProps) => {
  const running = data.executionState === 'running';
  const selectedModel = data.config?.model ?? 'gpt-5.6-luna';
  const modelOptions = MODEL_OPTIONS.some((option) => option.value === selectedModel)
    ? MODEL_OPTIONS
    : [{ value: selectedModel, label: `${selectedModel} · 설정값` }, ...MODEL_OPTIONS];

  return (
    <NodeShell
      accent="#e11d48"
      icon={Sparkles}
      eyebrow="Output Module"
      title="LLM Reader Answer"
      state={getExecutionNodeState(data.executionState)}
      selected={selected}
      width={380}
      inputPorts={['question_text', 'context_json']}
      bodyClassName="space-y-3"
    >
      <div className="space-y-1.5">
        <label className="node-field-label" htmlFor={`reader-model-${id}`}>
          <Bot className="h-3 w-3 text-rose-600" /> 답변 생성 LLM 모델
        </label>
        <select
          id={`reader-model-${id}`}
          className="nodrag nopan w-full cursor-pointer rounded-lg border border-rose-200 bg-rose-50/60 px-2.5 py-1.5 text-xs font-medium text-rose-950 outline-none focus:border-rose-500 focus:ring-2 focus:ring-rose-100 disabled:cursor-wait disabled:opacity-60"
          value={selectedModel}
          disabled={running}
          onPointerDown={(event) => event.stopPropagation()}
          onChange={(event) => data.onConfigChange?.({ model: event.currentTarget.value })}
        >
          {modelOptions.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
      </div>
      {running && (
        <div className="flex items-center gap-2 text-[10px] font-semibold text-rose-700">
          <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> 근거 기반 답변 생성 중
        </div>
      )}
    </NodeShell>
  );
};
