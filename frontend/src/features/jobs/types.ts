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
  error: string | null;
}
