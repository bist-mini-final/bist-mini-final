import { useCallback, useEffect, useState } from 'react';
import { Boxes, CircleAlert, Clock3, RefreshCw } from 'lucide-react';
import { Button, PageHeader, StatusBadge, Surface } from '../../shared/ui';
import { jobsApi } from './api';
import type {
  KubernetesResourceSummary,
  KubernetesWorkloadSnapshot,
  WorkflowLeaseSummary,
} from './types';
import './jobs.css';

const POLL_INTERVAL_MS = 5_000;

export function isRunningKubernetesJob(resource: KubernetesResourceSummary): boolean {
  return resource.kind === 'Job' && resource.active === true;
}

export function isRunningWorkflowLease(run: WorkflowLeaseSummary): boolean {
  return run.status === 'running';
}

function formattedTime(value: string | null): string {
  if (!value) return '-';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString('ko-KR');
}

function ResourceTable({
  title,
  description,
  resources,
}: {
  title: string;
  description: string;
  resources: KubernetesResourceSummary[];
}) {
  return (
    <Surface className="jobs-panel">
      <header className="jobs-panel__header">
        <div>
          <h2>{title}</h2>
          <p>{description}</p>
        </div>
        <span className="jobs-count">{resources.length}</span>
      </header>
      <div className="jobs-table-wrap">
        <table className="jobs-table">
          <thead>
            <tr>
              <th>이름</th>
              <th>상태</th>
              <th>실행 중</th>
              <th>성공 / 실패</th>
              <th>생성 시각</th>
              <th>메시지</th>
            </tr>
          </thead>
          <tbody>
            {resources.length === 0 ? (
              <tr>
                <td className="jobs-table__empty" colSpan={6}>현재 표시할 리소스가 없습니다.</td>
              </tr>
            ) : resources.map((resource) => (
              <tr key={`${resource.kind}:${resource.namespace}:${resource.name}`}>
                <td>
                  <strong>{resource.name}</strong>
                  <small>{resource.kind}</small>
                </td>
                <td>
                  <StatusBadge tone={resource.active ? 'info' : resource.failed ? 'danger' : 'neutral'}>
                    {resource.status}
                  </StatusBadge>
                </td>
                <td>{resource.active == null ? '-' : resource.active ? '예' : '아니요'}</td>
                <td>{resource.succeeded ?? 0} / {resource.failed ?? 0}</td>
                <td>{formattedTime(resource.created_at)}</td>
                <td className="jobs-table__message">{resource.message ?? '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Surface>
  );
}

function duration(value: number | null): string {
  if (value == null) return '-';
  return value >= 60 ? `${Math.floor(value / 60)}분 ${Math.round(value % 60)}초` : `${Math.round(value)}초`;
}

function LeaseTable({ runs }: { runs: WorkflowLeaseSummary[] }) {
  return (
    <Surface className="jobs-panel">
      <header className="jobs-panel__header">
        <div><h2>실행 중 Workflow Queue / Lease</h2><p>현재 워커가 처리 중인 PostgreSQL 작업</p></div>
        <span className="jobs-count">{runs.length}</span>
      </header>
      <div className="jobs-table-wrap">
        <table className="jobs-table jobs-table--leases">
          <thead><tr><th>Run / Workflow</th><th>Queue</th><th>상태</th><th>Worker / K8s</th><th>Heartbeat / TTL</th><th>시도</th></tr></thead>
          <tbody>
            {runs.length === 0 ? <tr><td className="jobs-table__empty" colSpan={6}>현재 실행 중인 큐 작업이 없습니다.</td></tr> : runs.map((run) => (
              <tr key={run.run_id}>
                <td><strong>{run.run_id}</strong><small>{run.workflow_id}</small></td>
                <td>{run.queue_name}<small>priority {run.priority}</small></td>
                <td><StatusBadge tone={run.lease_stale ? 'danger' : run.status === 'running' ? 'success' : 'neutral'}>{run.lease_stale ? 'Lease stale' : run.status}</StatusBadge>{run.cancel_requested ? <small>취소 요청됨</small> : null}</td>
                <td>{run.worker_id ?? '-'}<small>{run.kubernetes_resource ?? 'K8s 미연결'}</small></td>
                <td>{duration(run.heartbeat_age_seconds)} 경과<small>TTL {duration(run.lease_ttl_seconds)} · {formattedTime(run.heartbeat_at)}</small></td>
                <td>{run.attempt_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Surface>
  );
}

export function JobsView() {
  const [snapshot, setSnapshot] = useState<KubernetesWorkloadSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const load = useCallback(async (signal?: AbortSignal) => {
    setIsLoading(true);
    try {
      const next = await jobsApi.snapshot(signal);
      setSnapshot(next);
      setError(next.available ? null : next.error ?? 'Kubernetes에 연결할 수 없습니다.');
    } catch (loadError) {
      if (signal?.aborted) return;
      setError(loadError instanceof Error ? loadError.message : '작업 상태 조회에 실패했습니다.');
    } finally {
      if (!signal?.aborted) setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    let controller = new AbortController();
    void load(controller.signal);
    const timer = window.setInterval(() => {
      controller.abort();
      controller = new AbortController();
      void load(controller.signal);
    }, POLL_INTERVAL_MS);
    return () => {
      window.clearInterval(timer);
      controller.abort();
    };
  }, [load]);

  const runningJobs = (snapshot?.jobs ?? []).filter(isRunningKubernetesJob);
  const runningLeases = (snapshot?.workflow_runs ?? []).filter(isRunningWorkflowLease);

  return (
    <div className="jobs-page">
      <PageHeader
        className="jobs-header"
        eyebrow="READ-ONLY OPERATIONS"
        title="Kubernetes 작업 관제"
        description="현재 실행 중인 Workflow와 Kubernetes Batch Job만 5초마다 갱신합니다."
        actions={(
          <Button type="button" busy={isLoading} onClick={() => void load()} disabled={isLoading}>
            <RefreshCw size={15} className={isLoading ? 'jobs-spin' : ''} />
            새로고침
          </Button>
        )}
      />

      {error && (
        <div className="jobs-alert" role="alert">
          <CircleAlert size={18} />
          <div><strong>클러스터 상태를 확인할 수 없습니다.</strong><span>{error}</span></div>
        </div>
      )}

      {snapshot && !snapshot.queue_available && (
        <div className="jobs-alert jobs-alert--warning" role="status">
          <CircleAlert size={18} />
          <div><strong>큐/Lease 상태를 확인할 수 없습니다.</strong><span>{snapshot.queue_error ?? 'PostgreSQL 조회 실패'}</span></div>
        </div>
      )}

      <section className="jobs-summary" aria-label="Kubernetes 상태 요약">
        <article><Boxes size={18} /><span>실행 중 Job<strong>{runningJobs.length}</strong></span></article>
        <article><Clock3 size={18} /><span>실행 중 Workflow<strong>{runningLeases.length}</strong></span></article>
        <article><Clock3 size={18} /><span>마지막 수집<strong>{formattedTime(snapshot?.collected_at ?? null)}</strong></span></article>
        <article><span className="jobs-source-dot" /><span>조회 경로<strong>{snapshot?.source ?? '-'}</strong></span></article>
      </section>

      <div className="jobs-context">
        <span>Namespace <strong>{snapshot?.namespace ?? 'bist-batch'}</strong></span>
        <span>Context <strong>{snapshot?.context ?? '-'}</strong></span>
      </div>

      <LeaseTable runs={runningLeases} />

      <ResourceTable
        title="실행 중 Batch Jobs"
        description="현재 active 상태인 Kubernetes Job"
        resources={runningJobs}
      />
    </div>
  );
}
