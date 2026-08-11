import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';
import {
  ArrowDownToLine,
  ArrowUpFromLine,
  Braces,
  CheckCircle2,
  Clock3,
  Database,
  History,
  Settings2,
  Workflow,
  X,
} from 'lucide-react';
import type {
  JsonSchema,
  ModuleDefinition,
  OutputBranch,
  WorkflowRun,
} from '../../types';
import {
  DEFAULT_JSON_PREVIEW_LIMITS,
  formatJsonPreview,
} from '../../utils/jsonPreview';

interface ModulePreview {
  label: string;
  input: unknown;
  output: unknown;
}

interface ModuleSettingsModalProps {
  nodeId: string;
  definition: ModuleDefinition;
  config: Record<string, unknown>;
  onConfigChange: (patch: Record<string, unknown>) => void;
  runs: WorkflowRun[];
  preview?: ModulePreview;
  onClose: () => void;
}

interface BranchPresentation {
  label: string;
  dotClass: string;
  activeClass: string;
  noteClass: string;
}

const BRANCH_PRESENTATION: Record<OutputBranch, BranchPresentation> = {
  cached: {
    label: '캐시 적중',
    dotClass: 'bg-blue-600',
    activeClass: 'bg-blue-600 text-white',
    noteClass: 'border-blue-200 bg-blue-50 text-blue-900',
  },
  generated: {
    label: '새로 생성',
    dotClass: 'bg-emerald-600',
    activeClass: 'bg-emerald-600 text-white',
    noteClass: 'border-emerald-200 bg-emerald-50 text-emerald-900',
  },
};

const DEFAULT_BRANCH_PRESENTATION: BranchPresentation = {
  label: '분기 출력',
  dotClass: 'bg-slate-600',
  activeClass: 'bg-slate-700 text-white',
  noteClass: 'border-slate-200 bg-slate-50 text-slate-800',
};

function branchPresentation(branch: OutputBranch): BranchPresentation {
  return BRANCH_PRESENTATION[branch] ?? DEFAULT_BRANCH_PRESENTATION;
}

function schemaReference(schema: JsonSchema, root: JsonSchema): JsonSchema {
  if (!schema.$ref?.startsWith('#/$defs/')) return schema;
  const name = decodeURIComponent(schema.$ref.slice('#/$defs/'.length));
  return root.$defs?.[name] ?? schema;
}

function effectiveSchema(schema: JsonSchema, root: JsonSchema): JsonSchema {
  const resolved = schemaReference(schema, root);
  const concrete = resolved.anyOf?.find((option) => option.type !== 'null');
  return concrete
    ? { ...resolved, ...schemaReference(concrete, root), description: resolved.description }
    : resolved;
}

function typeLabel(schema: JsonSchema, root: JsonSchema): string {
  const resolved = effectiveSchema(schema, root);
  const nullable = schema.anyOf?.some((option) => option.type === 'null');
  let label: string;

  if (Array.isArray(resolved.type)) {
    label = resolved.type.join(' | ');
  } else if (resolved.type === 'array') {
    label = `array<${resolved.items ? typeLabel(resolved.items, root) : 'any'}>`;
  } else if (resolved.type) {
    label = resolved.type;
  } else if (resolved.properties) {
    label = 'object';
  } else if (resolved.additionalProperties) {
    label = `object<string, ${
      typeof resolved.additionalProperties === 'object'
        ? typeLabel(resolved.additionalProperties, root)
        : 'any'
    }>`;
  } else {
    label = 'any';
  }
  return nullable ? `${label} | null` : label;
}

function displayValue(value: unknown): string {
  if (typeof value === 'string') return value || '""';
  const serialized = JSON.stringify(value);
  return serialized === undefined ? String(value) : serialized;
}

function formatRunTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('ko-KR', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(date);
}

interface JsonPayloadPreviewProps {
  label: string;
  value: unknown;
}

function JsonPayloadPreview({ label, value }: JsonPayloadPreviewProps) {
  const preview = useMemo(() => formatJsonPreview(value), [value]);
  return (
    <div>
      <span>
        {label}
        <small>
          최대 {DEFAULT_JSON_PREVIEW_LIMITS.maxLines}줄
          {preview.truncated ? ' · 일부 생략됨' : ''}
        </small>
      </span>
      <pre>{preview.text}</pre>
    </div>
  );
}

interface LazyHistoryDetailsProps {
  badge: string;
  badgeTone: string;
  dataKind: string;
  defaultOpen: boolean;
  error?: string | null;
  icon: ReactNode;
  input: unknown;
  output: unknown;
  showInput?: boolean;
  skipReason?: string | null;
  subtitle: string;
  title: string;
}

function LazyHistoryDetails({
  badge,
  badgeTone,
  dataKind,
  defaultOpen,
  error,
  icon,
  input,
  output,
  showInput = true,
  skipReason,
  subtitle,
  title,
}: LazyHistoryDetailsProps) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <details
      className="module-execution-history__item"
      data-kind={dataKind}
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>
        <span className="module-execution-history__icon">{icon}</span>
        <span className="module-execution-history__summary">
          <strong>{title}</strong>
          <small>{subtitle}</small>
        </span>
        <span className="module-execution-history__badge" data-tone={badgeTone}>
          {badge}
        </span>
      </summary>
      {error && <p className="module-execution-history__error">{error}</p>}
      {skipReason && <p className="module-execution-history__skip">{skipReason}</p>}
      {open && (
        <div className="module-execution-history__payloads">
          {showInput && <JsonPayloadPreview label="INPUT" value={input} />}
          <JsonPayloadPreview label="OUTPUT" value={output} />
        </div>
      )}
    </details>
  );
}

function LazyRawSchema({ schema }: { schema: JsonSchema }) {
  const [open, setOpen] = useState(false);
  return (
    <details
      className="module-schema-panel__raw"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary><Braces className="h-3.5 w-3.5" /> 원본 JSON Schema</summary>
      {open && <pre>{JSON.stringify(schema, null, 2)}</pre>}
    </details>
  );
}

function schemaRules(schema: JsonSchema, root: JsonSchema): string[] {
  const resolved = effectiveSchema(schema, root);
  const rules: string[] = [];
  if (Object.prototype.hasOwnProperty.call(resolved, 'default')) {
    rules.push(`기본값 ${displayValue(resolved.default)}`);
  }
  if (resolved.minimum !== undefined) rules.push(`최솟값 ${resolved.minimum}`);
  if (resolved.maximum !== undefined) rules.push(`최댓값 ${resolved.maximum}`);
  if (resolved.exclusiveMinimum !== undefined) rules.push(`${resolved.exclusiveMinimum} 초과`);
  if (resolved.exclusiveMaximum !== undefined) rules.push(`${resolved.exclusiveMaximum} 미만`);
  if (resolved.minLength !== undefined) rules.push(`최소 ${resolved.minLength}자`);
  if (resolved.maxLength !== undefined) rules.push(`최대 ${resolved.maxLength}자`);
  if (resolved.pattern) rules.push(`정규식 ${resolved.pattern}`);
  if (resolved.format) rules.push(`형식 ${resolved.format}`);
  if (resolved.enum) rules.push(`허용값 ${resolved.enum.map(displayValue).join(', ')}`);
  return rules;
}

interface SchemaFieldProps {
  name: string;
  schema: JsonSchema;
  root: JsonSchema;
  required: boolean;
  role: string;
  depth?: number;
}

function SchemaField({
  name,
  schema,
  root,
  required,
  role,
  depth = 0,
}: SchemaFieldProps) {
  const resolved = effectiveSchema(schema, root);
  const properties = resolved.properties ?? {};
  const nestedRequired = new Set(resolved.required ?? []);
  const rules = schemaRules(schema, root);
  const entries = Object.entries(properties);

  return (
    <article className="schema-field" data-depth={depth}>
      <div className="schema-field__heading">
        <code>{name}</code>
        <span className="schema-field__type">{typeLabel(schema, root)}</span>
      </div>
      <div className="schema-field__badges">
        <span data-tone={required ? 'required' : 'optional'}>
          {required ? '필수' : '선택'}
        </span>
        <span>{role}</span>
      </div>
      {resolved.description && <p>{resolved.description}</p>}
      {rules.length > 0 && (
        <div className="schema-field__rules">
          {rules.map((rule) => <span key={rule}>{rule}</span>)}
        </div>
      )}
      {entries.length > 0 && depth < 3 && (
        <div className="schema-field__children">
          {entries.map(([childName, childSchema]) => (
            <SchemaField
              key={childName}
              name={childName}
              schema={childSchema}
              root={root}
              required={nestedRequired.has(childName)}
              role="하위 필드"
              depth={depth + 1}
            />
          ))}
        </div>
      )}
      {resolved.type === 'array' && resolved.items && depth < 3 && (
        <div className="schema-field__children">
          <SchemaField
            name="items[]"
            schema={resolved.items}
            root={root}
            required
            role="배열 항목"
            depth={depth + 1}
          />
        </div>
      )}
    </article>
  );
}

interface SchemaPanelProps {
  title: string;
  description: string;
  schema: JsonSchema;
  ports: string[];
  direction: 'input' | 'output';
  branchSchemas?: Partial<Record<OutputBranch, JsonSchema>>;
  branchOutputs?: Partial<Record<OutputBranch, string>>;
  rawValue?: boolean;
}

function SchemaPanel({
  title,
  description,
  schema,
  ports,
  direction,
  branchSchemas = {},
  branchOutputs = {},
  rawValue = false,
}: SchemaPanelProps) {
  const branchNames = useMemo(
    () => Object.keys(branchSchemas) as OutputBranch[],
    [branchSchemas]
  );
  const [selectedBranch, setSelectedBranch] = useState<OutputBranch | null>(
    branchNames[0] ?? null
  );
  useEffect(() => {
    setSelectedBranch((current) =>
      current && branchNames.includes(current) ? current : branchNames[0] ?? null
    );
  }, [branchNames]);

  const activeSchema = selectedBranch
    ? branchSchemas[selectedBranch] ?? schema
    : schema;
  const properties = activeSchema.properties ?? {};
  const required = new Set(activeSchema.required ?? []);
  const Icon = direction === 'input' ? ArrowDownToLine : ArrowUpFromLine;
  const propertyEntries = Object.entries(properties);
  const fieldEntries: [string, JsonSchema][] = propertyEntries.length > 0
    ? propertyEntries
    : rawValue
      ? [['$', activeSchema]]
      : [];

  const fieldRole = (name: string) => {
    if (rawValue && name === '$') {
      return direction === 'input' ? '연결된 원본 JSON 전체' : '원본 그대로 출력';
    }
    if (ports.includes(name)) return direction === 'input' ? '연결 입력 포트' : '출력 포트';
    return direction === 'input' ? '실행 입력' : '실행 메타데이터';
  };

  return (
    <section className="module-schema-panel" data-direction={direction}>
      <header>
        <span className="module-schema-panel__icon"><Icon className="h-4 w-4" /></span>
        <div>
          <h3>{title}</h3>
          <p>{description}</p>
        </div>
        <span className="module-schema-panel__count">{fieldEntries.length}</span>
      </header>

      {direction === 'output' && branchNames.length > 0 && (
        <div className="p-3 bg-slate-50/90 border-b border-slate-200/80 space-y-2.5">
          <div className="flex items-center justify-between text-xs">
            <span className="font-bold text-slate-800">분기별 Output DTO</span>
            <span className="text-[10px] text-slate-500">백엔드 모듈 계약 기준</span>
          </div>
          <div
            className="grid gap-1 p-1 bg-slate-200/70 border border-slate-200 rounded-xl text-[11px]"
            style={{ gridTemplateColumns: `repeat(${branchNames.length}, minmax(0, 1fr))` }}
          >
            {branchNames.map((branch) => {
              const presentation = branchPresentation(branch);
              return (
                <button
                  key={branch}
                  type="button"
                  onClick={() => setSelectedBranch(branch)}
                  className={`py-1.5 px-2 rounded-lg font-bold transition-colors cursor-pointer text-center ${
                    selectedBranch === branch
                      ? presentation.activeClass
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                  }`}
                >
                  {presentation.label} ({branch})
                </button>
              );
            })}
          </div>
          {selectedBranch && (() => {
            const presentation = branchPresentation(selectedBranch);
            const outputPort = branchOutputs[selectedBranch];
            return (
              <div className={`px-2.5 py-1.5 border rounded-lg text-[11px] leading-snug ${presentation.noteClass}`}>
                <strong>{presentation.label}</strong> 실행 시 <code>{outputPort}</code> 포트 DTO만 전달합니다.
              </div>
            );
          })()}
        </div>
      )}

      <div className="module-schema-panel__fields">
        {fieldEntries.length > 0 ? fieldEntries.map(([name, fieldSchema]: [string, JsonSchema]) => (
          <SchemaField
            key={name}
            name={name}
            schema={fieldSchema}
            root={activeSchema}
            required={required.has(name)}
            role={fieldRole(name)}
          />
        )) : <p className="module-schema-panel__empty">정의된 필드가 없습니다.</p>}
      </div>
      <LazyRawSchema schema={activeSchema} />
    </section>
  );
}

interface AutoResizeTextareaProps {
  value: string;
  onChange: (value: string) => void;
}

function AutoResizeTextarea({ value, onChange }: AutoResizeTextareaProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = '0px';
    textarea.style.height = `${textarea.scrollHeight + 2}px`;
  }, [value]);

  return (
    <textarea
      ref={textareaRef}
      value={value}
      rows={1}
      onChange={(event) => onChange(event.currentTarget.value)}
    />
  );
}

export function ModuleSettingsModal({
  nodeId,
  definition,
  config,
  onConfigChange,
  runs,
  preview,
  onClose,
}: ModuleSettingsModalProps) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeButtonRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const configEntries = Object.entries(config);
  const configPreview = useMemo(() => formatJsonPreview(config), [config]);
  const executionHistory = useMemo(() => runs.flatMap((run) => {
    const state = run.nodes[nodeId];
    if (!state) return [];
    if (
      state.status === 'pending' &&
      state.input_payload === null &&
      state.output === null &&
      state.error === null
    ) return [];
    return [{ run, state }];
  }).slice(0, 20), [nodeId, runs]);

  return createPortal(
    <div className="module-settings-overlay" role="presentation" onMouseDown={onClose}>
      <section
        className="module-settings-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="module-settings-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="module-settings-modal__header">
          <div className="module-settings-modal__mark"><Settings2 className="h-5 w-5" /></div>
          <div className="module-settings-modal__heading">
            <div className="module-settings-modal__eyebrow">
              <span>{definition.category} Module</span>
              <code>{nodeId}</code>
            </div>
            <h2 id="module-settings-title">{definition.label}</h2>
            <p>{definition.description}</p>
          </div>
          <div className="module-settings-modal__meta">
            <span>v{definition.version}</span>
            <span><Database className="h-3 w-3" /> {definition.cacheable ? '캐시 사용' : '캐시 안 함'}</span>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            className="module-settings-modal__close"
            onClick={onClose}
            aria-label="상세 설정 닫기"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="module-settings-modal__body">
          <SchemaPanel
            title="Input Schema"
            description="실행 전에 백엔드 DTO가 검증하는 필드"
            schema={definition.input_schema}
            ports={definition.inputs}
            direction="input"
            rawValue={definition.raw_input}
          />

          <aside className="module-contract-summary">
            <div className="module-contract-summary__title">
              <Workflow className="h-4 w-4" />
              <h3>연결 및 필드 규칙</h3>
            </div>
            <ul>
              <li><CheckCircle2 className="h-3.5 w-3.5" /> 연결선은 출력 포트명을 대상 입력 포트명으로 전달합니다.</li>
              <li><CheckCircle2 className="h-3.5 w-3.5" /> 필수 입력이 없거나 타입이 다르면 실행 전에 422 오류로 중단됩니다.</li>
              <li><CheckCircle2 className="h-3.5 w-3.5" /> 출력도 DTO 검증을 통과해야 캐시와 다음 모듈에 저장됩니다.</li>
              <li><CheckCircle2 className="h-3.5 w-3.5" /> 노드 설정은 워크플로 JSON의 <code>config</code> 필드에 유지됩니다.</li>
            </ul>

            <div className="module-contract-summary__ports">
              <div>
                <span>INPUT PORTS</span>
                {definition.inputs.length > 0
                  ? definition.inputs.map((port) => <code key={port}>{port}</code>)
                  : <small>연결 입력 없음</small>}
              </div>
              <div>
                <span>OUTPUT PORTS</span>
                {definition.outputs.length > 0
                  ? definition.outputs.map((port) => <code key={port}>{port}</code>)
                  : <small>출력 없음</small>}
              </div>
              {Object.entries(definition.branch_outputs).length > 0 && (
                <div className="module-contract-summary__branches">
                  <span>BRANCH OUTPUTS</span>
                  {(Object.entries(definition.branch_outputs) as [OutputBranch, string][]).map(
                    ([branch, outputPort]) => {
                      const presentation = branchPresentation(branch);
                      return (
                        <code key={branch} data-branch={branch}>
                          <i className={presentation.dotClass} />
                          {presentation.label} · {outputPort}
                        </code>
                      );
                    }
                  )}
                </div>
              )}
            </div>

            <div className="module-contract-summary__config">
              <span>CURRENT NODE CONFIG</span>
              <div className="module-contract-summary__config-fields">
                {definition.config_presets.length > 0 && (() => {
                  const presetSchema = definition.config_schema.properties?.preset;
                  const resolvedPresetSchema = presetSchema
                    ? effectiveSchema(presetSchema, definition.config_schema)
                    : undefined;
                  const selectedPresetId = typeof config.preset === 'string'
                    ? config.preset
                    : typeof resolvedPresetSchema?.default === 'string'
                      ? resolvedPresetSchema.default
                      : definition.config_presets[0].id;
                  return (
                    <label className="module-contract-summary__config-preset">
                      <span><code>preset</code>프롬프트 프리셋과 기본 내용을 함께 적용합니다.</span>
                      <select
                        value={selectedPresetId}
                        onChange={(event) => {
                          const preset = definition.config_presets.find(
                            (candidate) => candidate.id === event.currentTarget.value
                          );
                          if (preset) onConfigChange(preset.values);
                        }}
                      >
                        {definition.config_presets.map((preset) => (
                          <option key={preset.id} value={preset.id}>{preset.label}</option>
                        ))}
                      </select>
                    </label>
                  );
                })()}
                {definition.config_fields.map((fieldName) => {
                  if (fieldName === 'preset' && definition.config_presets.length > 0) return null;
                  const fieldSchema = definition.config_schema.properties?.[fieldName];
                  if (!fieldSchema) return null;
                  const resolved = effectiveSchema(fieldSchema, definition.config_schema);
                  const value = config[fieldName] ?? resolved.default;
                  if (resolved.type === 'number' || resolved.type === 'integer') {
                    return (
                      <label key={fieldName}>
                        <span><code>{fieldName}</code>{resolved.description}</span>
                        <input
                          type="number"
                          value={typeof value === 'number' ? value : ''}
                          min={resolved.minimum}
                          max={resolved.maximum}
                          step={resolved.type === 'integer' ? 1 : 0.01}
                          onChange={(event) => {
                            const nextValue = event.currentTarget.valueAsNumber;
                            if (Number.isFinite(nextValue)) {
                              onConfigChange({ [fieldName]: nextValue });
                            }
                          }}
                        />
                      </label>
                    );
                  }
                  if (resolved.type === 'boolean') {
                    return (
                      <label key={fieldName} className="module-contract-summary__config-toggle">
                        <span><code>{fieldName}</code>{resolved.description}</span>
                        <input
                          type="checkbox"
                          checked={Boolean(value)}
                          onChange={(event) => onConfigChange({ [fieldName]: event.currentTarget.checked })}
                        />
                      </label>
                    );
                  }
                  if (resolved.type === 'string') {
                    const stringValue = typeof value === 'string' ? value : '';
                    const multiline = fieldName.includes('prompt') || fieldName.includes('instruction');
                    const enumValues = resolved.enum?.filter(
                      (candidate): candidate is string => typeof candidate === 'string'
                    );
                    return (
                      <label key={fieldName} className={multiline ? 'module-contract-summary__config-textarea' : undefined}>
                        <span><code>{fieldName}</code>{resolved.description}</span>
                        {enumValues && enumValues.length > 0 ? (
                          <select
                            value={stringValue}
                            onChange={(event) => onConfigChange({ [fieldName]: event.currentTarget.value })}
                          >
                            {enumValues.map((option) => (
                              <option key={option} value={option}>{option}</option>
                            ))}
                          </select>
                        ) : multiline ? (
                          <AutoResizeTextarea
                            value={stringValue}
                            onChange={(nextValue) => onConfigChange({ [fieldName]: nextValue })}
                          />
                        ) : (
                          <input
                            type="text"
                            value={stringValue}
                            onChange={(event) => onConfigChange({ [fieldName]: event.currentTarget.value })}
                          />
                        )}
                      </label>
                    );
                  }
                  return null;
                })}
              </div>
              {configEntries.length > 0
                ? <pre>{configPreview.text}</pre>
                : <p>저장된 사용자 설정이 없어 DTO 기본값을 사용합니다.</p>}
            </div>

            <section className="module-execution-history">
              <div className="module-execution-history__heading">
                <History className="h-4 w-4" />
                <div>
                  <h3>캐시 및 실행 이력</h3>
                  <p>캔버스에서 숨긴 입력·출력 데이터</p>
                </div>
                <span>{executionHistory.length + (preview ? 1 : 0)}</span>
              </div>

              {preview && (
                <LazyHistoryDetails
                  badge="미리보기"
                  badgeTone="preview"
                  dataKind="preview"
                  defaultOpen
                  icon={<Clock3 className="h-3.5 w-3.5" />}
                  input={preview.input}
                  output={preview.output}
                  showInput={preview.input !== null}
                  subtitle="아직 실행 이력에 저장되지 않은 현재 결과"
                  title={preview.label}
                />
              )}

              {executionHistory.map(({ run, state }, index) => {
                const badgeTone = state.status === 'failed'
                  ? 'failed'
                  : state.status === 'skipped'
                    ? 'skipped'
                    : state.outcome === 'cached'
                      ? 'cache'
                      : 'generated';
                const badge = state.status === 'failed'
                  ? '실패'
                  : state.status === 'skipped'
                    ? '건너뜀'
                    : state.outcome === 'cached'
                      ? '캐시 적중'
                      : '새로 생성';
                return (
                  <LazyHistoryDetails
                    key={run.id}
                    badge={badge}
                    badgeTone={badgeTone}
                    dataKind={state.status === 'skipped' ? 'skipped' : state.outcome === 'cached' ? 'cache' : state.status}
                    defaultOpen={!preview && index === 0}
                    error={state.error}
                    icon={<Database className="h-3.5 w-3.5" />}
                    input={state.input_payload}
                    output={state.output}
                    skipReason={state.skip_reason}
                    subtitle={`Batch ${state.batch_index + 1} · ${run.id}`}
                    title={formatRunTime(state.completed_at ?? state.started_at ?? run.updated_at)}
                  />
                );
              })}

              {!preview && executionHistory.length === 0 && (
                <div className="module-execution-history__empty">
                  이 노드에 저장된 실행 또는 캐시 이력이 없습니다.
                </div>
              )}
            </section>
          </aside>

          <SchemaPanel
            title="Output Schema"
            description="실행 후 다음 모듈과 캐시에 전달되는 필드"
            schema={definition.output_schema}
            ports={definition.outputs}
            direction="output"
            branchSchemas={definition.branch_schemas}
            branchOutputs={definition.branch_outputs}
            rawValue={definition.raw_output}
          />
        </div>
      </section>
    </div>,
    document.body
  );
}
