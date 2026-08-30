import { DatabaseZap, X } from 'lucide-react';
import { Button, IconButton } from '../../../shared/ui';
import { useModalDialog } from './useModalDialog';

interface ResetDataDialogProps {
  readonly companyName: string;
  readonly onConfirm: () => void;
  readonly onClose: () => void;
}

export function ResetDataDialog({
  companyName,
  onConfirm,
  onClose,
}: ResetDataDialogProps) {
  const dialogRef = useModalDialog();

  return (
    <dialog
      ref={dialogRef}
      className="bi-dialog"
      aria-labelledby="bi-data-reset-title"
      onClose={onClose}
      onCancel={(event) => { event.preventDefault(); onClose(); }}
    >
      <div className="bi-dialog__header">
        <div>
          <span className="bi-dialog__eyebrow">RESET DASHBOARD DATA</span>
          <h2 id="bi-data-reset-title">{companyName} 데이터를 다시 만들까요?</h2>
        </div>
        <IconButton variant="ghost" aria-label="데이터 초기화 확인 닫기" onClick={onClose}>
          <X size={18} aria-hidden="true" />
        </IconButton>
      </div>
      <p className="bi-dialog__empty">
        이 기업의 현재 원본에 연결된 지표 질문과 답변을 모두 제거한 뒤,
        새 질문을 LLM으로 병렬 처리합니다. 현재 대시보드는 새 스냅샷이 완성될 때까지 유지됩니다.
      </p>
      <div className="bi-dialog__actions">
        <Button type="button" onClick={onClose}>취소</Button>
        <Button variant="danger-solid" type="button" onClick={onConfirm}>
          <DatabaseZap size={16} aria-hidden="true" />삭제 후 재생성
        </Button>
      </div>
    </dialog>
  );
}
