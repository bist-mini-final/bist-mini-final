import { Plus, X } from 'lucide-react';
import { Button, IconButton } from '../../../shared/ui';
import { getCardDefinition } from '../config/cardRegistry';
import type { BiCardId } from '../types';
import { useModalDialog } from './useModalDialog';

interface CardLibraryDialogProps {
  readonly hiddenCardIds: readonly BiCardId[];
  readonly onRestore: (cardId: BiCardId) => void;
  readonly onClose: () => void;
}

export function CardLibraryDialog({ hiddenCardIds, onRestore, onClose }: CardLibraryDialogProps) {
  const dialogRef = useModalDialog();

  return (
    <dialog
      ref={dialogRef}
      className="bi-dialog"
      aria-labelledby="bi-card-library-title"
      onClose={onClose}
      onCancel={(event) => { event.preventDefault(); onClose(); }}
    >
      <div className="bi-dialog__header">
        <div>
          <span className="bi-dialog__eyebrow">CARD LIBRARY</span>
          <h2 id="bi-card-library-title">카드 추가</h2>
        </div>
        <IconButton variant="ghost" aria-label="카드 목록 닫기" onClick={onClose}><X size={18} aria-hidden="true" /></IconButton>
      </div>
      {hiddenCardIds.length === 0 ? (
        <p className="bi-dialog__empty">추가할 수 있는 카드가 없습니다. 숨긴 카드와 새로 등록된 카드는 이곳에 표시됩니다.</p>
      ) : (
        <ul className="bi-card-library">
          {hiddenCardIds.map((cardId) => {
            const card = getCardDefinition(cardId);
            return (
              <li key={cardId}>
                <div><strong>{card.title}</strong><span>{card.description}</span></div>
                <Button size="sm" type="button" onClick={() => onRestore(cardId)}><Plus size={16} aria-hidden="true" />추가</Button>
              </li>
            );
          })}
        </ul>
      )}
    </dialog>
  );
}
