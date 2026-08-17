import type { Node, NodeProps } from '@xyflow/react';
import { Boxes } from 'lucide-react';
import type { JsonSchema, ModuleDefinition } from '../../types';
import { getExecutionNodeState, NodeShell } from '../FlowNode/NodeShell';

interface GenericModuleNodeData extends Record<string, unknown> {
  executionState?: string;
  moduleDefinition?: ModuleDefinition;
  nodeWidth?: number;
  onNodeWidthChange?: (width: number) => void;
  onValuesChange?: (patch: Record<string, unknown>) => void;
  values?: Record<string, unknown>;
}

export type GenericModuleNodeProps = NodeProps<Node<GenericModuleNodeData>>;

function concreteSchema(schema: JsonSchema): JsonSchema {
  const concrete = schema.anyOf?.find((candidate) => candidate.type !== 'null');
  return concrete ? { ...schema, ...concrete } : schema;
}

function SourceInputField({
  name,
  schema,
  value,
  onChange,
}: {
  name: string;
  schema: JsonSchema;
  value: unknown;
  onChange: (value: unknown) => void;
}) {
  const resolved = concreteSchema(schema);
  const nullable = schema.anyOf?.some((candidate) => candidate.type === 'null') ?? false;
  const effectiveValue = value ?? resolved.default;
  const options = resolved.enum?.filter(
    (candidate): candidate is string => typeof candidate === 'string'
  );

  if (resolved.type === 'boolean') {
    return (
      <label className="flex items-center justify-between gap-2 text-[10px] text-slate-700">
        <span><code>{name}</code> {resolved.description}</span>
        <input
          className="nodrag nopan"
          type="checkbox"
          checked={Boolean(effectiveValue)}
          onChange={(event) => onChange(event.currentTarget.checked)}
        />
      </label>
    );
  }

  if (resolved.type === 'integer' || resolved.type === 'number') {
    return (
      <label className="block space-y-1 text-[10px] text-slate-700">
        <span><code>{name}</code> {resolved.description}</span>
        <input
          className="nodrag nopan w-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs"
          type="number"
          value={typeof effectiveValue === 'number' ? effectiveValue : ''}
          min={resolved.minimum}
          max={resolved.maximum}
          step={resolved.type === 'integer' ? 1 : 0.01}
          onChange={(event) => {
            const nextValue = event.currentTarget.valueAsNumber;
            if (Number.isFinite(nextValue)) onChange(nextValue);
          }}
        />
      </label>
    );
  }

  const stringValue = typeof effectiveValue === 'string' ? effectiveValue : '';
  return (
    <label className="block space-y-1 text-[10px] text-slate-700">
      <span><code>{name}</code> {resolved.description}</span>
      {options && options.length > 0 ? (
        <select
          className="nodrag nopan w-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs"
          value={stringValue}
          onChange={(event) => onChange(
            nullable && event.currentTarget.value === '' ? null : event.currentTarget.value
          )}
        >
          {nullable && <option value="">선택 안 함</option>}
          {options.map((option) => <option key={option} value={option}>{option}</option>)}
        </select>
      ) : (
        <input
          className="nodrag nopan w-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs"
          type="text"
          value={stringValue}
          placeholder={nullable ? '선택 입력' : name}
          onChange={(event) => onChange(
            nullable && event.currentTarget.value === '' ? null : event.currentTarget.value
          )}
        />
      )}
    </label>
  );
}

export const GenericModuleNode = ({ data, selected }: GenericModuleNodeProps) => {
  const definition = data.moduleDefinition;
  const inputs = definition?.inputs ?? [];
  const outputs = definition?.outputs ?? [];
  const branches = Object.keys(definition?.branch_outputs ?? {});
  const sourceInputFields = definition?.inputs.length === 0
    ? Object.entries(definition.input_schema.properties ?? {})
    : [];
  const outputHandles = branches.length > 0
    ? branches
    : outputs.length > 1
      ? outputs
      : [];

  return (
    <NodeShell
      accent="#64748b"
      icon={Boxes}
      eyebrow={`${definition?.category ?? 'Pipeline'} Module`}
      title={definition?.label ?? 'Backend Module'}
      state={getExecutionNodeState(data.executionState)}
      nodeData={data}
      selected={selected}
      width={data.nodeWidth ?? 360}
      onWidthChange={data.onNodeWidthChange}
      hasInput={inputs.length > 0}
      inputPorts={inputs}
      hasOutput={outputs.length > 0}
      outputBranches={outputHandles}
      bodyClassName="space-y-2"
    >
      <p className="text-[10px] leading-4 text-slate-600">
        {definition?.description ?? '백엔드가 제공한 DTO 계약으로 실행되는 모듈입니다.'}
      </p>
      {sourceInputFields.length > 0 && (
        <div className="space-y-2 rounded-lg border border-slate-200 bg-slate-50 p-2.5">
          <strong className="block text-[10px] text-slate-700">실행 Input</strong>
          {sourceInputFields.map(([name, schema]) => (
            <SourceInputField
              key={name}
              name={name}
              schema={schema}
              value={data.values?.[name]}
              onChange={(nextValue) => data.onValuesChange?.({ [name]: nextValue })}
            />
          ))}
        </div>
      )}
      <div className="rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-2 text-[10px] text-slate-600">
        Input {inputs.join(', ') || '없음'} · Output {outputs.join(', ') || '없음'}
      </div>
    </NodeShell>
  );
};
