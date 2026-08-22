import { CircleAlert, LoaderCircle } from 'lucide-react';
import type { BiRefreshState } from '../types';

interface BiPageNoticeProps {
  readonly refresh: BiRefreshState;
}

const PROCESSING_STATUSES = ['queued', 'indexing', 'profiling', 'extracting', 'materializing'] as const;

export function BiPageNotice({ refresh }: BiPageNoticeProps) {
  const isProcessing = PROCESSING_STATUSES.some((status) => status === refresh.status);
  if (!isProcessing && refresh.status !== 'failed') return null;

  if (refresh.status === 'failed') {
    return (
      <div className="bi-page-notice" data-tone="warning" role="status">
        <CircleAlert size={18} aria-hidden="true" />
        <div><strong>새 데이터 처리를 완료하지 못했습니다.</strong><span>{refresh.message ?? '이전 스냅샷을 계속 표시합니다.'}</span></div>
      </div>
    );
  }

  return (
    <div className="bi-page-notice" data-tone="processing" role="status" aria-live="polite">
      <LoaderCircle className="bi-page-notice__spinner" size={18} aria-hidden="true" />
      <div><strong>새 데이터 처리 중</strong><span>{refresh.message ?? '완료될 때까지 이전 스냅샷을 계속 볼 수 있습니다.'}</span></div>
    </div>
  );
}
