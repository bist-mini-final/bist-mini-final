import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, DatabaseZap, LoaderCircle, X } from 'lucide-react';
import { Button, IconButton, StatusBadge } from '../../../shared/ui';
import {
  createBiMaterialization,
  fetchBiMaterializationCandidates,
  streamBiMaterializationJob,
} from '../services/api';
import type {
  BiMaterializationCandidate,
  BiMaterializationCandidateReason,
  BiMaterializationJob,
} from '../types';

const SNAPSHOT_MANAGER_DIALOG_ID = 'bi-snapshot-manager-dialog';
const COMPANY_NAME_COLLATOR = new Intl.Collator(['en-US', 'ko-KR'], {
  sensitivity: 'base',
  numeric: true,
});

const REASON_LABELS: Readonly<Record<BiMaterializationCandidateReason, string>> = {
  not_created: '미생성',
  source_changed: '원본 변경됨',
  failed: '생성 실패 · 재시도',
};

interface SnapshotManagerProps {
  readonly onMaterialized: (companyId: string) => Promise<void>;
}

interface SnapshotManagerDialogProps extends SnapshotManagerProps {
  readonly onClose: () => void;
}

function progressMessage(job: BiMaterializationJob | null): string {
  if (!job) return '스냅샷 생성 요청을 등록하는 중입니다.';
  if (job.totalRequests > 0) {
    return `${job.message ?? '재무 지표를 생성하고 있습니다.'} (${job.completedRequests}/${job.totalRequests})`;
  }
  return job.message ?? '스냅샷 생성 작업을 실행하고 있습니다.';
}

function SnapshotManagerDialog({ onMaterialized, onClose }: SnapshotManagerDialogProps) {
  const requestControllerRef = useRef<AbortController | null>(null);
  const [candidates, setCandidates] = useState<readonly BiMaterializationCandidate[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [job, setJob] = useState<BiMaterializationJob | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const sortedCandidates = useMemo(
    () => [...candidates].sort((left, right) => (
      COMPANY_NAME_COLLATOR.compare(left.displayName, right.displayName)
      || left.companyId.localeCompare(right.companyId)
    )),
    [candidates],
  );
  const selectedCandidate = candidates.find((candidate) => candidate.companyId === selectedId) ?? null;

  useEffect(() => {
    const controller = new AbortController();
    requestControllerRef.current = controller;
    const load = async () => {
      try {
        const response = await fetchBiMaterializationCandidates(controller.signal);
        if (controller.signal.aborted) return;
        setCandidates(response.candidates);
        setSelectedId((current) => (
          response.candidates.some((candidate) => candidate.companyId === current)
            ? current
            : ''
        ));
      } catch (error) {
        if (!controller.signal.aborted) {
          setErrorMessage(error instanceof Error
            ? '스냅샷 생성 후보를 불러오지 못했습니다.'
            : '스냅샷 생성 후보를 확인할 수 없습니다.');
        }
      } finally {
        if (!controller.signal.aborted) setIsLoading(false);
      }
    };
    void load();
    return () => requestControllerRef.current?.abort();
  }, []);

  const createSnapshot = async () => {
    if (!selectedCandidate || isCreating) return;
    requestControllerRef.current?.abort();
    const controller = new AbortController();
    requestControllerRef.current = controller;
    setIsCreating(true);
    setErrorMessage(null);
    setJob(null);
    try {
      const accepted = await createBiMaterialization({
        companyId: selectedCandidate.companyId,
        displayName: selectedCandidate.displayName,
        source: selectedCandidate.source,
      }, controller.signal);
      const completed = await streamBiMaterializationJob(
        accepted.jobId,
        setJob,
        controller.signal,
      );
      if (controller.signal.aborted) return;
      if (completed.status === 'failed') {
        setErrorMessage(completed.message ?? 'BI 스냅샷 생성에 실패했습니다.');
        return;
      }
      await onMaterialized(selectedCandidate.companyId);
      if (!controller.signal.aborted) onClose();
    } catch (error) {
      if (!controller.signal.aborted) {
        setErrorMessage(error instanceof Error
          ? 'BI 스냅샷 생성 요청을 완료하지 못했습니다.'
          : 'BI 스냅샷 생성 중 오류가 발생했습니다.');
      }
    } finally {
      if (!controller.signal.aborted) setIsCreating(false);
    }
  };

  return (
    <div
      id={SNAPSHOT_MANAGER_DIALOG_ID}
      className="bi-dialog bi-snapshot-manager-dialog"
      role="dialog"
      aria-labelledby="bi-snapshot-manager-title"
    >
      <div className="bi-dialog__header">
        <div>
          <span className="bi-dialog__eyebrow">BI SNAPSHOT</span>
          <h2 id="bi-snapshot-manager-title">기업 스냅샷 추가</h2>
        </div>
        <IconButton variant="ghost" onClick={onClose} aria-label="기업 스냅샷 추가 닫기">
          <X size={18} aria-hidden="true" />
        </IconButton>
      </div>
      <p className="bi-company-dialog__status" aria-live="polite">
        {isCreating
          ? progressMessage(job)
          : errorMessage
            ?? '인덱싱된 기업 중 BI 스냅샷을 생성할 기업을 선택하세요.'}
      </p>
      <div className="bi-company-list" role="listbox" aria-label="스냅샷 생성 후보" aria-busy={isLoading || isCreating}>
        {isLoading ? <p className="bi-dialog__empty">생성 가능한 기업을 확인하는 중입니다.</p> : null}
        {!isLoading && sortedCandidates.length === 0 ? (
          <p className="bi-dialog__empty">추가로 생성할 기업 스냅샷이 없습니다.</p>
        ) : null}
        {sortedCandidates.map((candidate) => {
          const isSelected = candidate.companyId === selectedId;
          return (
            <Button
              key={candidate.companyId}
              className="bi-company-option bi-snapshot-candidate"
              type="button"
              role="option"
              aria-selected={isSelected}
              disabled={isCreating}
              onClick={() => setSelectedId(candidate.companyId)}
            >
              <span className="bi-snapshot-candidate__identity">
                <strong>{candidate.displayName}</strong>
                <small>{candidate.source.fileName}</small>
              </span>
              <StatusBadge
                className="bi-snapshot-candidate__status"
                tone={candidate.reason === 'failed'
                  ? 'danger'
                  : candidate.reason === 'source_changed'
                    ? 'warning'
                    : 'info'}
              >
                {REASON_LABELS[candidate.reason]}
              </StatusBadge>
              {isSelected ? <Check size={17} aria-hidden="true" /> : null}
            </Button>
          );
        })}
      </div>
      <div className="bi-dialog__actions">
        <Button type="button" onClick={onClose}>취소</Button>
        <Button
          variant="primary"
          type="button"
          disabled={!selectedCandidate || isCreating}
          onClick={() => { void createSnapshot(); }}
        >
          {isCreating
            ? <><LoaderCircle className="bi-page-notice__spinner" size={16} aria-hidden="true" /> 생성 중</>
            : <><DatabaseZap size={16} aria-hidden="true" /> 선택 기업 생성</>}
        </Button>
      </div>
    </div>
  );
}

export function SnapshotManager({ onMaterialized }: SnapshotManagerProps) {
  const [isOpen, setIsOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const close = () => {
    setIsOpen(false);
    window.setTimeout(() => triggerRef.current?.focus(), 0);
  };

  useEffect(() => {
    if (!isOpen) return undefined;
    const handlePointerDown = (event: PointerEvent) => {
      if (event.target instanceof Node && !containerRef.current?.contains(event.target)) close();
    };
    const handleKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') close();
    };
    document.addEventListener('pointerdown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen]);

  return (
    <div ref={containerRef} className="bi-snapshot-manager">
      <Button
        ref={triggerRef}
        size="sm"
        type="button"
        aria-controls={SNAPSHOT_MANAGER_DIALOG_ID}
        aria-expanded={isOpen}
        aria-haspopup="dialog"
        onClick={() => setIsOpen(true)}
      >
        <DatabaseZap size={15} aria-hidden="true" />
        기업 스냅샷 추가
      </Button>
      {isOpen ? (
        <SnapshotManagerDialog
          onMaterialized={onMaterialized}
          onClose={close}
        />
      ) : null}
    </div>
  );
}
