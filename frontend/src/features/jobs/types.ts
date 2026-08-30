export type KubernetesResourceKind = 'ScaledJob' | 'Job' | 'Pod';

export interface KubernetesResourceSummary {
  kind: KubernetesResourceKind;
  name: string;
  namespace: string;
  status: string;
  ready: boolean | null;
  active: boolean | null;
  succeeded: number | null;
  failed: number | null;
  created_at: string | null;
  message: string | null;
}

export interface KubernetesWorkloadSnapshot {
  available: boolean;
  source: 'in_cluster' | 'kubectl' | 'unavailable';
  namespace: string;
  context: string | null;
  collected_at: string;
  scaled_jobs: KubernetesResourceSummary[];
  jobs: KubernetesResourceSummary[];
  pods: KubernetesResourceSummary[];
  queue_available: boolean;
  workflow_runs: WorkflowLeaseSummary[];
  queue_error: string | null;
  error: string | null;
}

export interface WorkflowLeaseSummary {
  run_id: string;
  workflow_id: string;
  queue_name: string;
  status: string;
  worker_id: string | null;
  priority: number;
  attempt_count: number;
  available_at: string;
  claimed_at: string | null;
  heartbeat_at: string | null;
  heartbeat_age_seconds: number | null;
  lease_ttl_seconds: number | null;
  lease_stale: boolean;
  cancel_requested: boolean;
  created_at: string;
  updated_at: string;
  kubernetes_resource: string | null;
}
