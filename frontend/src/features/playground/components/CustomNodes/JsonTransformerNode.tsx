import { useEffect, useState } from 'react';
import type { Node, NodeProps } from '@xyflow/react';
import { FileCode, ArrowRight, Plus, Trash2 } from 'lucide-react';
import { getExecutionNodeState, NodeShell } from '../FlowNode/NodeShell';

interface MappingRule {
  id: string;
  sourceKey: string;
  targetKey: string;
}

interface JsonTransformerNodeData extends Record<string, unknown> {
  activeStep?: number;
  config?: { mappings?: Record<string, string> };
  onConfigChange?: (patch: Record<string, unknown>) => void;
  executionState?: string;
}

export type JsonTransformerNodeProps = NodeProps<Node<JsonTransformerNodeData>>;

const mappingRules = (mappings: Record<string, string> = {}): MappingRule[] =>
  Object.entries(mappings).map(([sourceKey, targetKey], index) => ({
    id: `configured-${index}`,
    sourceKey,
    targetKey,
  }));

export const JsonTransformerNode = ({ data, selected }: JsonTransformerNodeProps) => {
  const configuredMappings = data.config?.mappings;
  const [rules, setRules] = useState<MappingRule[]>(() => mappingRules(configuredMappings));
  const [customKey, setCustomKey] = useState('');
  const [customValue, setCustomValue] = useState('');
  const mappingSignature = JSON.stringify(configuredMappings ?? {});

  useEffect(() => {
    setRules(mappingRules(configuredMappings));
  }, [mappingSignature]);

  useEffect(() => {
    data.onConfigChange?.({
      mappings: Object.fromEntries(
        rules.map((rule) => [rule.sourceKey, rule.targetKey])
      ),
    });
  }, [data.onConfigChange, rules]);

  const addRule = () => {
    const sourceKey = customKey.trim();
    const targetKey = customValue.trim();
    if (sourceKey && targetKey) {
      const newRules = [
        ...rules.filter((rule) => rule.sourceKey !== sourceKey),
        { id: Date.now().toString(), sourceKey, targetKey },
      ];
      setRules(newRules);
      setCustomKey('');
      setCustomValue('');
    }
  };

  const removeRule = (id: string) => {
    setRules(rules.filter((rule) => rule.id !== id));
  };

  return (
    <NodeShell
      accent="#7c3aed"
      icon={FileCode}
      eyebrow="Transform Module"
      title="JSON Format Mapper / Converter"
      state={getExecutionNodeState(data.executionState)}
      nodeData={data}
      inputPorts={['any_json']}
      selected={selected}
      width={340}
      bodyClassName="space-y-3"
    >
        <div className="node-field-label text-slate-400">
          필드 매핑 규칙 (Source → Target Name)
        </div>

        <div className="space-y-1.5 max-h-36 overflow-y-auto pr-1">
          {rules.length === 0 && (
            <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-3 py-2 text-center text-[11px] text-slate-400">
              등록된 매핑 규칙이 없습니다.
            </div>
          )}
          {rules.map((rule) => (
            <div key={rule.id} className="p-2 bg-slate-50 border border-slate-200 rounded-lg flex items-center gap-2 text-xs">
              <span className="font-mono text-purple-700 font-medium truncate flex-1">{rule.sourceKey}</span>
              <ArrowRight className="w-3 h-3 text-slate-400 shrink-0" />
              <span className="font-mono text-emerald-700 font-semibold truncate flex-1">{rule.targetKey}</span>
              <button
                onClick={() => removeRule(rule.id)}
                className="text-slate-300 hover:text-rose-500 transition-colors p-0.5 cursor-pointer"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>

        {/* Add Rule Form */}
        <div className="p-2 bg-violet-50/60 border border-violet-100 rounded-xl space-y-2">
          <div className="text-[10px] font-semibold text-violet-800">새 변환 매핑 추가</div>
          <div className="grid grid-cols-2 gap-1.5">
            <input
              type="text"
              placeholder="Source Field"
              value={customKey}
              onChange={(e) => setCustomKey(e.target.value)}
              className="px-2 py-1 text-xs bg-white border border-violet-200 rounded-lg font-mono focus:outline-none focus:border-violet-500"
            />
            <input
              type="text"
              placeholder="Target Field"
              value={customValue}
              onChange={(e) => setCustomValue(e.target.value)}
              className="px-2 py-1 text-xs bg-white border border-violet-200 rounded-lg font-mono focus:outline-none focus:border-violet-500"
            />
          </div>
          <button
            onClick={addRule}
            className="w-full py-1 bg-violet-600 hover:bg-violet-700 text-white text-xs font-semibold rounded-lg flex items-center justify-center gap-1 transition-colors cursor-pointer"
          >
            <Plus className="w-3 h-3" /> 매핑 규칙 추가
          </button>
        </div>
    </NodeShell>
  );
};
