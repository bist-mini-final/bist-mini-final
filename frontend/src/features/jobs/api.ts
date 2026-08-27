import { requestJson } from '../../shared/api/httpClient';
import type { KubernetesWorkloadSnapshot } from './types';

export const jobsApi = {
  snapshot(signal?: AbortSignal): Promise<KubernetesWorkloadSnapshot> {
    return requestJson<KubernetesWorkloadSnapshot>(
      '/api/jobs',
      { signal },
      'Kubernetes 작업 상태를 불러오지 못했습니다.',
    );
  },
};
