import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  ArrowDownToLine,
  ArrowUpFromLine,
  BookOpen,
  Braces,
  Settings2,
  SlidersHorizontal,
  X,
} from 'lucide-react';
import type { JsonSchema, ModuleDefinition, WorkflowRun } from '../../types';
import {
  DEFAULT_JSON_PREVIEW_LIMITS,
  formatJsonPreview,
} from '../../utils/jsonPreview';
import { pipelineApi } from '../../services/api';
import './ModuleSettingsModal.css';

interface ModuleSettingsModalProps {
  nodeId: string;
  definition: ModuleDefinition;
  config: Record<string, unknown>;
  onConfigChange: (patch: Record<string, unknown>) => void;
  readOnly?: boolean;
  run?: WorkflowRun | null;
  onClose: () => void;
}

type RunNodeState = WorkflowRun['nodes'][string];

const STATUS_LABELS: Record<RunNodeState['status'], string> = {
  pending: '대기 중',
  running: '실행 중',
  succeeded: '완료',
  failed: '실패',
  skipped: '건너뜀',
};

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

function configDto(
  definition: ModuleDefinition,
  config: Record<string, unknown>,
): Record<string, unknown> {
  const defaults = Object.fromEntries(definition.config_fields.flatMap((fieldName) => {
    const fieldSchema = definition.config_schema.properties?.[fieldName];
    if (!fieldSchema) return [];
    const resolved = effectiveSchema(fieldSchema, definition.config_schema);
    return Object.prototype.hasOwnProperty.call(resolved, 'default')
      ? [[fieldName, resolved.default] as const]
      : [];
  }));
  return { ...defaults, ...config };
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

interface RuntimeDtoPanelProps {
  direction: 'input' | 'output';
  value: unknown;
  state?: RunNodeState;
  run?: WorkflowRun | null;
}

function RuntimeDtoPanel({ direction, value, state, run }: RuntimeDtoPanelProps) {
  const isInput = direction === 'input';
  const preview = useMemo(() => formatJsonPreview(value), [value]);
  const empty = value === null || value === undefined;
  const Icon = isInput ? ArrowDownToLine : ArrowUpFromLine;
  const title = isInput ? 'Input DTO' : 'Output DTO';
  const emptyMessage = isInput
    ? '현재 실행에서 이 모듈로 전달된 입력이 없습니다.'
    : state?.status === 'running'
      ? '모듈 실행 중입니다. 출력이 생성되면 여기에 표시됩니다.'
      : '현재 실행에서 생성된 출력이 없습니다.';

  return (
    <section className="module-state-panel" data-direction={direction}>
      <header className="module-state-panel__header">
        <span className="module-state-panel__icon"><Icon className="h-4 w-4" /></span>
        <div>
          <h3>{title}</h3>
          <p>{isInput ? '현재 모듈에 들어온 값' : '현재 모듈에서 나간 값'}</p>
        </div>
        <span className="module-state-panel__status" data-status={state?.status ?? 'idle'}>
          {state ? STATUS_LABELS[state.status] : '실행 전'}
        </span>
      </header>

      <div className="module-state-panel__context">
        <span>{state ? `Batch ${state.batch_index + 1}` : '현재 실행 없음'}</span>
        {run && <code title={run.id}>{run.id}</code>}
        {state?.elapsed_ms != null && <span>{state.elapsed_ms.toLocaleString()}ms</span>}
      </div>

      <div className="module-state-panel__payload">
        {state?.error && !isInput && (
          <p className="module-state-panel__error" role="alert">{state.error}</p>
        )}
        {state?.skip_reason && !isInput && (
          <p className="module-state-panel__skip">{state.skip_reason}</p>
        )}
        {empty ? (
          <div className="module-state-panel__empty">{emptyMessage}</div>
        ) : (
          <>
            <div className="module-state-panel__payload-meta">
              <span>CURRENT VALUE</span>
              <small>
                최대 {DEFAULT_JSON_PREVIEW_LIMITS.maxLines}줄
                {preview.truncated ? ' · 일부 생략됨' : ''}
              </small>
            </div>
            <pre>{preview.text}</pre>
          </>
        )}
      </div>
    </section>
  );
}

interface ConfigDtoPanelProps {
  definition: ModuleDefinition;
  config: Record<string, unknown>;
  onConfigChange: (patch: Record<string, unknown>) => void;
  readOnly: boolean;
  state?: RunNodeState;
}

function ConfigDtoPanel({
  definition,
  config,
  onConfigChange,
  readOnly,
  state,
}: ConfigDtoPanelProps) {
  const dto = useMemo(() => {
    if (state && Object.keys(state.config_payload).length > 0) {
      return state.config_payload;
    }
    return configDto(definition, config);
  }, [config, definition, state]);
  const dtoPreview = useMemo(() => formatJsonPreview(dto), [dto]);

  return (
    <section className="module-state-panel module-config-panel" data-direction="config">
      <header className="module-state-panel__header">
        <span className="module-state-panel__icon"><SlidersHorizontal className="h-4 w-4" /></span>
        <div>
          <h3>Config DTO</h3>
          <p>현재 모듈에 적용되는 설정값</p>
        </div>
        <span className="module-state-panel__status" data-status={readOnly ? 'readonly' : 'editable'}>
          {readOnly ? '읽기 전용' : '편집 가능'}
        </span>
      </header>

      <div className="module-config-panel__content">
        {readOnly && (
          <p className="module-config-panel__readonly" role="note">
            표준 Job의 설정은 읽기 전용입니다. 변경하려면 워크플로를 복제하세요.
          </p>
        )}
        <fieldset
          className="module-config-panel__fields"
          disabled={readOnly}
          aria-label="모듈 설정 입력"
        >
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
              <label>
                <span><code>preset</code>프롬프트 프리셋과 기본 내용을 함께 적용합니다.</span>
                <select
                  value={selectedPresetId}
                  onChange={(event) => {
                    const preset = definition.config_presets.find(
                      (candidate) => candidate.id === event.currentTarget.value,
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
                      if (Number.isFinite(nextValue)) onConfigChange({ [fieldName]: nextValue });
                    }}
                  />
                </label>
              );
            }

            if (resolved.type === 'boolean') {
              return (
                <label key={fieldName}>
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
                (candidate): candidate is string => typeof candidate === 'string',
              );
              const configuredOptions = (resolved as Record<string, unknown>).options as string[] | undefined;
              const modelOptions = fieldName === 'model' && definition.type.includes('embedder')
                ? ['text-embedding-3-small', 'text-embedding-3-large']
                : undefined;
              const selectOptions = configuredOptions ?? enumValues ?? modelOptions;

              return (
                <label key={fieldName} className={multiline ? 'module-config-panel__textarea' : undefined}>
                  <span><code>{fieldName}</code>{resolved.description}</span>
                  {selectOptions && selectOptions.length > 0 ? (
                    <div className="module-config-panel__select-with-custom">
                      <select
                        value={selectOptions.includes(stringValue) ? stringValue : '__custom__'}
                        onChange={(event) => {
                          const selected = event.currentTarget.value;
                          if (selected !== '__custom__') onConfigChange({ [fieldName]: selected });
                        }}
                      >
                        {selectOptions.map((option) => (
                          <option key={option} value={option}>{option}</option>
                        ))}
                        <option value="__custom__">직접 입력 (Custom)...</option>
                      </select>
                      {(!selectOptions.includes(stringValue) || stringValue === '') && (
                        <input
                          type="text"
                          value={stringValue}
                          placeholder="직접 입력"
                          onChange={(event) => onConfigChange({ [fieldName]: event.currentTarget.value })}
                        />
                      )}
                    </div>
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
        </fieldset>

        <div className="module-config-panel__dto">
          <div>
            <span><Braces className="h-3.5 w-3.5" /> CURRENT CONFIG DTO</span>
            {state && <small>Batch {state.batch_index + 1} 실행 기준</small>}
          </div>
          <pre>{dtoPreview.text}</pre>
        </div>
      </div>
    </section>
  );
}

export function ModuleSettingsModal({
  nodeId,
  definition,
  config,
  onConfigChange,
  readOnly = false,
  run = null,
  onClose,
}: ModuleSettingsModalProps) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const summaryState = run?.nodes[nodeId];
  const [state, setState] = useState<RunNodeState | undefined>(summaryState);

  useEffect(() => {
    closeButtonRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  useEffect(() => {
    setState(summaryState);
    if (!run) return undefined;

    const controller = new AbortController();
    pipelineApi.getRunNode(run.id, nodeId, controller.signal)
      .then((detail) => setState(detail))
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === 'AbortError')) {
          setState(summaryState);
        }
      });
    return () => controller.abort();
  }, [nodeId, run, summaryState]);

  return createPortal(
    <div
      className="module-settings-overlay"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        className="module-settings-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="module-settings-title"
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
            {state && <span data-status={state.status}>{STATUS_LABELS[state.status]}</span>}
            <span>v{definition.version}</span>
            {run && <span>{formatRunTime(run.updated_at)}</span>}
            <a href={definition.documentation_url} target="_blank" rel="noreferrer">
              <BookOpen className="h-3 w-3" />
              <span>Markdown 문서</span>
            </a>
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
          <RuntimeDtoPanel direction="input" value={state?.input_payload} state={state} run={run} />
          <ConfigDtoPanel
            definition={definition}
            config={config}
            onConfigChange={onConfigChange}
            readOnly={readOnly}
            state={state}
          />
          <RuntimeDtoPanel direction="output" value={state?.output} state={state} run={run} />
        </div>
      </section>
    </div>,
    document.body,
  );
}
