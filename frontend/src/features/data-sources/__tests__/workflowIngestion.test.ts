import { describe, expect, it } from 'vitest';
import type { IngestionJobResponse } from '../types';
import { pipelineFromIngestionJob } from '../workflowIngestion';

describe('pipelineFromIngestionJob', () => {
  it('keeps Luna inspection available before the index writer completes', () => {
    const job = {
      job_id: 'run-partial',
      status: 'running',
      workflow_id: 'indexing_pgvector',
      worker_active: true,
      index: null,
      luna_output: {
        file_name: 'sample.xlsm',
        workbook_hash: 'a'.repeat(64),
        sheet_names: ['Key_Stats'],
        tables: [{ sheet_name: 'Key_Stats' }],
      },
      run: {
        schema_version: 1,
        id: 'run-partial',
        workflow_id: 'indexing_pgvector',
        workflow_updated_at: '2026-08-19T00:00:00Z',
        status: 'running',
        created_at: '2026-08-19T00:00:00Z',
        updated_at: '2026-08-19T00:00:01Z',
        orchestration: {
          backend: 'prefect',
          deployment_name: 'excel-ingestion/excel-ingestion-docker',
          external_run_id: 'prefect-flow-run-123',
          submission_attempt: 1,
          submitted_at: '2026-08-19T00:00:00Z',
        },
        graph: {
          nodes: [
            { id: 'selector', module_type: 'processed_file_selector', position: { x: 0, y: 0 }, config: {} },
            { id: 'luna', module_type: 'luna_vlm_structure_detector', position: { x: 0, y: 0 }, config: {} },
            { id: 'embedder', module_type: 'cell_text_embedder', position: { x: 0, y: 0 }, config: {} },
          ],
          edges: [],
          viewport: { x: 0, y: 0, zoom: 1 },
        },
        runtime_inputs: { selector: { file_name: 'sample.xlsm' } },
        use_cache: true,
        batches: [
          { index: 0, node_ids: ['selector'], status: 'completed', started_at: null, completed_at: null },
          { index: 1, node_ids: ['luna'], status: 'completed', started_at: null, completed_at: null },
          { index: 2, node_ids: ['embedder'], status: 'running', started_at: null, completed_at: null },
        ],
        nodes: Object.fromEntries(['selector', 'luna', 'embedder'].map((id, index) => [id, {
          node_id: id,
          module_type: index === 0
            ? 'processed_file_selector'
            : index === 1
              ? 'luna_vlm_structure_detector'
              : 'cell_text_embedder',
          batch_index: index,
          status: index < 2 ? 'succeeded' : 'running',
          input_payload: null,
          config_payload: {},
          output: null,
          error: null,
          cache_key: null,
          cache_hit: false,
          outcome: index < 2 ? 'generated' : null,
          skip_reason: null,
          started_at: null,
          completed_at: null,
          progress: {},
        }])),
      },
    } satisfies IngestionJobResponse;

    job.run.nodes.embedder.progress = {
      phase: 'embedding_batches',
      completed_batches: 3,
      total_batches: 10,
      completed_items: 6144,
      total_items: 20000,
    };
    const pipeline = pipelineFromIngestionJob(job);

    expect(pipeline.workbookHash).toBe('a'.repeat(64));
    expect(pipeline.lunaOutput?.sheet_names).toEqual(['Key_Stats']);
    expect(pipeline.lunaOutput?.tables).toHaveLength(1);
    expect(pipeline.modules[2].batchProgress).toEqual({
      completed: 3,
      total: 10,
      completedItems: 6144,
      totalItems: 20000,
    });
    expect(pipeline.modules[2].liveProgress).toMatchObject({
      label: '임베딩 생성',
      completed: 3,
      total: 10,
      unit: '배치',
      percent: 30,
    });
    expect(pipeline.progressPercent).toBe(77);
    expect(pipeline.scheduler).toEqual({
      backend: 'prefect',
      deploymentName: 'excel-ingestion/excel-ingestion-docker',
      externalRunId: 'prefect-flow-run-123',
      workerActive: true,
    });
    expect(pipeline.modules[2].sublogs[0].msg).toContain('3/10 배치 완료');
  });

  it('safely skips missing batch node IDs or missing nodes entries', () => {
    const job = {
      job_id: 'run-missing-node',
      status: 'running',
      workflow_id: 'indexing_pgvector',
      worker_active: true,
      index: null,
      luna_output: null,
      run: {
        schema_version: 1,
        id: 'run-missing-node',
        workflow_id: 'indexing_pgvector',
        workflow_updated_at: '2026-08-19T00:00:00Z',
        status: 'running',
        created_at: '2026-08-19T00:00:00Z',
        updated_at: '2026-08-19T00:00:01Z',
        graph: {
          nodes: [
            { id: 'valid-node', module_type: 'processed_file_selector', position: { x: 0, y: 0 }, config: {} },
          ],
          edges: [],
          viewport: { x: 0, y: 0, zoom: 1 },
        },
        runtime_inputs: {},
        use_cache: true,
        batches: [
          { index: 0, node_ids: ['valid-node', 'missing-node-1'], status: 'completed', started_at: null, completed_at: null },
          { index: 1, node_ids: ['missing-node-2'], status: 'running', started_at: null, completed_at: null },
        ],
        nodes: {
          'valid-node': {
            node_id: 'valid-node',
            module_type: 'processed_file_selector',
            batch_index: 0,
            status: 'succeeded',
            input_payload: null,
            config_payload: {},
            output: null,
            error: null,
            cache_key: null,
            cache_hit: false,
            outcome: 'generated',
            skip_reason: null,
            started_at: null,
            completed_at: null,
            progress: {},
          },
        },
      },
    } satisfies IngestionJobResponse;

    const pipeline = pipelineFromIngestionJob(job);
    expect(pipeline.modules).toHaveLength(1);
    expect(pipeline.modules[0].id).toBe('valid-node');
  });
});
