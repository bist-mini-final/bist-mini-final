import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ModuleDefinition } from '../../types';
import { ModuleSettingsModal } from './ModuleSettingsModal';

vi.mock('../../services/api', () => ({
  pipelineApi: {
    getRunNode: vi.fn(() => new Promise(() => undefined)),
  },
}));

const definition: ModuleDefinition = {
  type: 'test_module',
  label: 'Test Module',
  category: 'Logic',
  description: '설정 패널 테스트 모듈',
  inputs: ['input'],
  outputs: ['output'],
  branch_outputs: {},
  config_fields: ['top_k'],
  config_presets: [],
  raw_input: false,
  raw_output: false,
  version: '1',
  cacheable: true,
  task: {
    engine: 'kubernetes',
    enabled: true,
    retries: 0,
    retry_delay_seconds: 0,
    timeout_seconds: null,
    tags: [],
    resource_profile: 'interactive',
  },
  input_schema: { type: 'object', properties: {} },
  config_schema: {
    type: 'object',
    properties: {
      top_k: { type: 'integer', default: 5, minimum: 1, maximum: 100 },
    },
  },
  output_schema: { type: 'object', properties: {} },
  execution_schema: { type: 'object', properties: {} },
  documentation_url: '/docs/test-module',
  branch_schemas: {},
};

describe('ModuleSettingsModal', () => {
  it('opens standard workflow settings in read-only mode', () => {
    render(
      <ModuleSettingsModal
        nodeId="node-1"
        definition={definition}
        config={{ top_k: 10 }}
        onConfigChange={vi.fn()}
        readOnly
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByRole('dialog', { name: 'Test Module' })).toBeInTheDocument();
    expect(screen.getByRole('note')).toHaveTextContent('표준 Job의 설정은 읽기 전용');
    expect(screen.getByRole('spinbutton')).toBeDisabled();
  });

  it('updates configuration for an editable workflow', () => {
    const onConfigChange = vi.fn();
    render(
      <ModuleSettingsModal
        nodeId="node-1"
        definition={definition}
        config={{ top_k: 10 }}
        onConfigChange={onConfigChange}
        onClose={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '20' } });
    expect(onConfigChange).toHaveBeenCalledWith({ top_k: 20 });
  });

  it('shows only the current input, config, and output DTO values', () => {
    render(
      <ModuleSettingsModal
        nodeId="node-1"
        definition={definition}
        config={{ top_k: 10 }}
        onConfigChange={vi.fn()}
        run={{
          schema_version: 1,
          id: 'run-current',
          workflow_id: 'workflow-1',
          workflow_updated_at: '2026-08-30T00:00:00Z',
          status: 'running',
          created_at: '2026-08-30T00:00:00Z',
          updated_at: '2026-08-30T00:00:01Z',
          graph: { nodes: [], edges: [], viewport: { x: 0, y: 0, zoom: 1 } },
          runtime_inputs: {},
          use_cache: false,
          batches: [],
          nodes: {
            'node-1': {
              node_id: 'node-1',
              module_type: 'test_module',
              batch_index: 0,
              status: 'succeeded',
              input_payload: { query: '현재 질문' },
              config_payload: { top_k: 10 },
              output: { answer: '현재 답변' },
              error: null,
              cache_key: null,
              cache_hit: false,
              outcome: 'generated',
              skip_reason: null,
              started_at: '2026-08-30T00:00:00Z',
              completed_at: '2026-08-30T00:00:01Z',
            },
          },
        }}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByRole('heading', { name: 'Input DTO' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Config DTO' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Output DTO' })).toBeInTheDocument();
    expect(screen.getByText(/현재 질문/)).toBeInTheDocument();
    expect(screen.getByText(/현재 답변/)).toBeInTheDocument();
    expect(screen.queryByText('Input Schema')).not.toBeInTheDocument();
    expect(screen.queryByText('캐시 및 실행 이력')).not.toBeInTheDocument();
  });
});
