import { useCallback, useEffect, useState } from 'react';
import { Boxes, CheckCircle2, CircleAlert, Clock3, RefreshCw } from 'lucide-react';
import { jobsApi } from './api';
import type {
  KubernetesResourceSummary,
  KubernetesWorkloadSnapshot,
} from './types';
import './jobs.css';

const POLL_INTERVAL_MS = 5_000;

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
    <section className="jobs-panel">
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
              <th>Ready</th>
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
                  <span className="jobs-status" data-status={resource.status.toLowerCase()}>
                    {resource.status}
                  </span>
                </td>
                <td>{resource.ready == null ? '-' : resource.ready ? '예' : '아니요'}</td>
                <td>{resource.succeeded ?? 0} / {resource.failed ?? 0}</td>
                <td>{formattedTime(resource.created_at)}</td>
                <td className="jobs-table__message">{resource.message ?? '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
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

  const total = (snapshot?.scaled_jobs.length ?? 0)
    + (snapshot?.jobs.length ?? 0)
    + (snapshot?.pods.length ?? 0);
  const ready = [...(snapshot?.scaled_jobs ?? []), ...(snapshot?.jobs ?? []), ...(snapshot?.pods ?? [])]
    .filter((resource) => resource.ready).length;

  return (
    <div className="jobs-page">
      <header className="jobs-header">
        <div>
          <span className="jobs-header__eyebrow">READ-ONLY OPERATIONS</span>
          <h1>Kubernetes 작업 관제</h1>
          <p>KEDA ScaledJob과 배치 Job, Pod의 현재 상태를 5초마다 갱신합니다.</p>
        </div>
        <button type="button" onClick={() => void load()} disabled={isLoading}>
          <RefreshCw size={15} className={isLoading ? 'jobs-spin' : ''} />
          새로고침
        </button>
      </header>

      {error && (
        <div className="jobs-alert" role="alert">
          <CircleAlert size={18} />
          <div><strong>클러스터 상태를 확인할 수 없습니다.</strong><span>{error}</span></div>
        </div>
      )}

      <section className="jobs-summary" aria-label="Kubernetes 상태 요약">
        <article><Boxes size={18} /><span>전체 리소스<strong>{total}</strong></span></article>
        <article><CheckCircle2 size={18} /><span>Ready<strong>{ready}</strong></span></article>
        <article><Clock3 size={18} /><span>마지막 수집<strong>{formattedTime(snapshot?.collected_at ?? null)}</strong></span></article>
        <article><span className="jobs-source-dot" /><span>조회 경로<strong>{snapshot?.source ?? '-'}</strong></span></article>
      </section>

      <div className="jobs-context">
        <span>Namespace <strong>{snapshot?.namespace ?? 'bist-batch'}</strong></span>
        <span>Context <strong>{snapshot?.context ?? '-'}</strong></span>
      </div>

      <ResourceTable
        title="KEDA ScaledJobs"
        description="큐 기반 자동 확장 작업 정의"
        resources={snapshot?.scaled_jobs ?? []}
      />
      <ResourceTable
        title="Batch Jobs"
        description="현재 실행 중이거나 완료된 Kubernetes Job"
        resources={snapshot?.jobs ?? []}
      />
      <ResourceTable
        title="Worker Pods"
        description="배치 작업을 실제로 처리하는 Pod"
        resources={snapshot?.pods ?? []}
      />
    </div>
  );
}
