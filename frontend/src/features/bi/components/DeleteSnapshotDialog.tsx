import { RefreshCw, Trash2, X } from 'lucide-react';
import { Button, IconButton } from '../../../shared/ui';
import { useModalDialog } from './useModalDialog';

interface DeleteSnapshotDialogProps {
  readonly companyName: string;
  readonly isDeleting: boolean;
  readonly errorMessage: string | null;
  readonly onConfirm: () => void;
  readonly onClose: () => void;
}

export function DeleteSnapshotDialog({
  companyName,
  isDeleting,
  errorMessage,
  onConfirm,
  onClose,
}: DeleteSnapshotDialogProps) {
  const dialogRef = useModalDialog();
  const closeIfIdle = () => {
    if (!isDeleting) onClose();
  };

  return (
    <dialog
      ref={dialogRef}
      className="bi-dialog"
      aria-labelledby="bi-snapshot-delete-title"
      aria-busy={isDeleting}
      onClose={closeIfIdle}
      onCancel={(event) => { event.preventDefault(); closeIfIdle(); }}
    >
      <div className="bi-dialog__header">
        <div>
          <span className="bi-dialog__eyebrow">DELETE BI SNAPSHOT</span>
          <h2 id="bi-snapshot-delete-title">{companyName} 스냅샷을 삭제할까요?</h2>
        </div>
        <IconButton
          variant="ghost"
          aria-label="스냅샷 삭제 확인 닫기"
          onClick={closeIfIdle}
          disabled={isDeleting}
        >
          <X size={18} aria-hidden="true" />
        </IconButton>
      </div>
      <p className="bi-dialog__empty">
        이 기업의 BI 스냅샷과 생성된 지표 질문·답변이 삭제됩니다.
        원본 Excel과 pgvector 인덱스는 유지되며, 기업 스냅샷 추가에서 다시 생성할 수 있습니다.
      </p>
      {errorMessage ? <p className="bi-dialog__error" role="alert">{errorMessage}</p> : null}
      <div className="bi-dialog__actions">
        <Button type="button" onClick={closeIfIdle} disabled={isDeleting}>취소</Button>
        <Button
          variant="danger-solid"
          type="button"
          busy={isDeleting}
          onClick={onConfirm}
          disabled={isDeleting}
        >
          {isDeleting
            ? <RefreshCw className="bi-refresh-button__spinner" size={16} aria-hidden="true" />
            : <Trash2 size={16} aria-hidden="true" />}
          {isDeleting ? '삭제 중...' : '스냅샷 삭제'}
        </Button>
      </div>
    </dialog>
  );
}
