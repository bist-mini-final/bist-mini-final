import { useState } from 'react';
import type { Node, NodeProps } from '@xyflow/react';
import {
  Bot,
  Check,
  ChevronDown,
  ChevronUp,
  Clock,
  Coins,
  Copy,
  Hash,
  LoaderCircle,
  Sparkles,
} from 'lucide-react';
import { getExecutionNodeState, NodeShell } from '../FlowNode/NodeShell';
import { unwrapModuleOutput } from '../../adapters/moduleOutput';
import { MarkdownAnswer, normalizeMarkdownTables } from '../MarkdownAnswer';

const MODEL_OPTIONS = [
  { value: 'gpt-5.6-luna', label: 'GPT-5.6 Luna · 효율 중심' },
  { value: 'gpt-5.6-terra', label: 'GPT-5.6 Terra · 균형' },
  { value: 'gpt-5.6-sol', label: 'GPT-5.6 Sol · 품질 중심' },
];

interface ReaderExecutionOutput extends Record<string, unknown> {
  answer?: string;
  answer_markdown?: string;
  model?: string;
  latency_seconds?: number;
  estimated_cost_usd?: number;
  api_usage?: {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
  };
  query_context?: {
    question?: string;
  };
}

interface ReaderNodeData extends Record<string, unknown> {
  executionState?: string;
  executionOutput?: unknown;
  output?: unknown;
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

  const [copied, setCopied] = useState(false);
  const [expanded, setExpanded] = useState(true);

  // Resolve output payload
  const outputPayload = unwrapModuleOutput<ReaderExecutionOutput>(
    data.executionOutput ?? data.output,
    'answer_json',
  ) ?? {};
  const answerText = normalizeMarkdownTables(outputPayload.answer ?? outputPayload.answer_markdown ?? '');
  const latency = outputPayload.latency_seconds;
  const cost = outputPayload.estimated_cost_usd;
  const tokens = outputPayload.api_usage?.total_tokens;
  const usedModel = outputPayload.model ?? selectedModel;

  const handleCopy = async () => {
    if (!answerText) return;
    try {
      await navigator.clipboard.writeText(answerText);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // ignore
    }
  };

  return (
    <NodeShell
      accent="#e11d48"
      icon={Sparkles}
      eyebrow="Output Module"
      title="LLM Reader Answer"
      state={getExecutionNodeState(data.executionState)}
      selected={selected}
      width={answerText ? 440 : 380}
      nodeData={data}
      inputPorts={['context_json']}
      bodyClassName="space-y-3"
    >
      {/* Model Selection */}
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
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      {/* Running State */}
      {running && (
        <div className="flex items-center gap-2 rounded-lg border border-rose-200 bg-rose-50/80 p-2.5 text-[11px] font-semibold text-rose-700">
          <LoaderCircle className="h-4 w-4 animate-spin text-rose-600" />
          <span>근거 컨텍스트 기반 고품질 답변 생성 중...</span>
        </div>
      )}

      {/* Self-Contained Answer Display Card */}
      {Boolean(answerText) && (
        <div className="nodrag nopan space-y-2 rounded-xl border border-rose-200/90 bg-gradient-to-b from-rose-50/70 to-white p-3 shadow-xs">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <Sparkles className="h-3.5 w-3.5 text-rose-600" />
              <span className="text-[11px] font-bold text-rose-950">생성된 최종 답변</span>
            </div>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={handleCopy}
                className="flex items-center gap-1 rounded-md border border-rose-200 bg-white px-2 py-0.5 text-[10px] font-medium text-rose-800 hover:bg-rose-50 transition-colors"
                title="답변 복사"
              >
                {copied ? (
                  <>
                    <Check className="h-3 w-3 text-emerald-600" />
                    <span className="text-emerald-700 font-semibold">복사됨</span>
                  </>
                ) : (
                  <>
                    <Copy className="h-3 w-3 text-rose-600" />
                    <span>복사</span>
                  </>
                )}
              </button>
              <button
                type="button"
                onClick={() => setExpanded(!expanded)}
                className="rounded-md border border-rose-200 bg-white p-0.5 text-rose-700 hover:bg-rose-50 transition-colors"
                title={expanded ? '답변 접기' : '답변 펼치기'}
              >
                {expanded ? (
                  <ChevronUp className="h-3.5 w-3.5" />
                ) : (
                  <ChevronDown className="h-3.5 w-3.5" />
                )}
              </button>
            </div>
          </div>

          {expanded && (
            <div className="max-h-72 overflow-y-auto rounded-lg border border-rose-100 bg-white p-3 text-xs text-slate-800 select-text">
              <MarkdownAnswer markdown={answerText} />
            </div>
          )}

          {/* Performance & Token Metrics Pills */}
          <div className="flex flex-wrap items-center gap-1.5 pt-1 text-[10px] text-slate-600">
            {typeof latency === 'number' && (
              <span className="inline-flex items-center gap-1 rounded-md bg-rose-100/70 px-2 py-0.5 font-medium text-rose-900">
                <Clock className="h-2.5 w-2.5 text-rose-600" />
                {latency.toFixed(2)}s
              </span>
            )}
            {typeof tokens === 'number' && (
              <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 font-medium text-slate-800">
                <Hash className="h-2.5 w-2.5 text-slate-500" />
                {tokens} tokens
              </span>
            )}
            {typeof cost === 'number' && cost > 0 && (
              <span className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-0.5 font-medium text-emerald-800 border border-emerald-200">
                <Coins className="h-2.5 w-2.5 text-emerald-600" />
                ${cost.toFixed(5)}
              </span>
            )}
            {usedModel && (
              <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-1.5 py-0.5 font-mono text-[9px] text-slate-600">
                {usedModel}
              </span>
            )}
          </div>
        </div>
      )}
    </NodeShell>
  );
};
