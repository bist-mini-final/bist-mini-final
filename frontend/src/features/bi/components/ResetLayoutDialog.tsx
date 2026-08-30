import { RotateCcw, X } from 'lucide-react';
import { Button, IconButton } from '../../../shared/ui';
import { useModalDialog } from './useModalDialog';

interface ResetLayoutDialogProps {
  readonly onConfirm: () => void;
  readonly onClose: () => void;
}

export function ResetLayoutDialog({ onConfirm, onClose }: ResetLayoutDialogProps) {
  const dialogRef = useModalDialog();

  return (
    <dialog
      ref={dialogRef}
      className="bi-dialog"
      aria-labelledby="bi-reset-title"
      onClose={onClose}
      onCancel={(event) => { event.preventDefault(); onClose(); }}
    >
      <div className="bi-dialog__header">
        <div>
          <span className="bi-dialog__eyebrow">RESET LAYOUT</span>
          <h2 id="bi-reset-title">기본 배치로 초기화할까요?</h2>
        </div>
        <IconButton variant="ghost" aria-label="초기화 확인 닫기" onClick={onClose}><X size={18} aria-hidden="true" /></IconButton>
      </div>
      <p className="bi-dialog__empty">카드 순서, 크기, 숨김 설정이 기본값으로 돌아갑니다. 기업 데이터는 변경되지 않습니다.</p>
      <div className="bi-dialog__actions">
        <Button type="button" onClick={onClose}>취소</Button>
        <Button variant="primary" type="button" onClick={onConfirm}>
          <RotateCcw size={16} aria-hidden="true" />초기화
        </Button>
      </div>
    </dialog>
  );
}
