import { describe, expect, it } from 'vitest';
import { findRestorableIngestionJob } from '../DataSourcesView';
import type { IngestionJobResponse } from '../types';

function ingestionJob(
  jobId: string,
  status: IngestionJobResponse['status']
): IngestionJobResponse {
  return {
    job_id: jobId,
    status,
    workflow_id: 'excel_ingestion',
    run: {} as IngestionJobResponse['run'],
    index: null,
    worker_active: status === 'running',
  };
}

describe('findRestorableIngestionJob', () => {
  it('skips completed and failed history for the same pending file', () => {
    const running = ingestionJob('run-running', 'running');

    expect(findRestorableIngestionJob([
      ingestionJob('run-completed', 'completed'),
      ingestionJob('run-failed', 'failed'),
      running,
    ])).toBe(running);
    expect(findRestorableIngestionJob([
      ingestionJob('run-completed', 'completed'),
      ingestionJob('run-failed', 'failed'),
    ])).toBeNull();
  });
});
