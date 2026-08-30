import { describe, expect, it } from 'vitest';
import {
  isRunningKubernetesJob,
  isRunningWorkflowLease,
} from '../JobsView';
import type {
  KubernetesResourceSummary,
  WorkflowLeaseSummary,
} from '../types';

function job(
  status: string,
  active: boolean | null,
  kind: KubernetesResourceSummary['kind'] = 'Job',
): KubernetesResourceSummary {
  return {
    kind,
    name: `${kind.toLowerCase()}-${status}`,
    namespace: 'bist-batch',
    status,
    ready: false,
    active,
    succeeded: 0,
    failed: 0,
    created_at: null,
    message: null,
  };
}

function lease(status: string): WorkflowLeaseSummary {
  return {
    run_id: `run-${status}`,
    workflow_id: 'rag_query',
    queue_name: 'workflow',
    status,
    worker_id: null,
    priority: 0,
    attempt_count: 0,
    available_at: '2026-08-30T00:00:00Z',
    claimed_at: null,
    heartbeat_at: null,
    heartbeat_age_seconds: null,
    lease_ttl_seconds: null,
    lease_stale: false,
    cancel_requested: false,
    created_at: '2026-08-30T00:00:00Z',
    updated_at: '2026-08-30T00:00:00Z',
    kubernetes_resource: null,
  };
}

describe('JobsView active workload filters', () => {
  it('keeps only active Kubernetes Jobs', () => {
    const resources = [
      job('Running', true),
      job('Pending', false),
      job('Complete', false),
      job('Running', true, 'Pod'),
    ];

    expect(resources.filter(isRunningKubernetesJob).map((item) => item.name))
      .toEqual(['job-Running']);
  });

  it('keeps only running workflow leases', () => {
    const runs = ['queued', 'running', 'paused', 'completed', 'failed'].map(lease);

    expect(runs.filter(isRunningWorkflowLease).map((item) => item.status))
      .toEqual(['running']);
  });
});
