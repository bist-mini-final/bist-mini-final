import { useEffect, useRef } from 'react';
import { Plus, X } from 'lucide-react';
import { getCardDefinition } from '../config/cardRegistry';
import type { BiCardId } from '../types';

interface CardLibraryDialogProps {
  readonly hiddenCardIds: readonly BiCardId[];
  readonly onRestore: (cardId: BiCardId) => void;
  readonly onClose: () => void;
}

export function CardLibraryDialog({ hiddenCardIds, onRestore, onClose }: CardLibraryDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    if (dialogRef.current && !dialogRef.current.open) dialogRef.current.showModal();
  }, []);

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
          <h2 id="bi-card-library-title">숨긴 카드 복구</h2>
        </div>
        <button type="button" aria-label="카드 목록 닫기" onClick={onClose}><X size={18} aria-hidden="true" /></button>
      </div>
      {hiddenCardIds.length === 0 ? (
        <p className="bi-dialog__empty">숨긴 카드가 없습니다. 배치 편집에서 카드를 숨기면 이곳에서 복구할 수 있습니다.</p>
      ) : (
        <ul className="bi-card-library">
          {hiddenCardIds.map((cardId) => {
            const card = getCardDefinition(cardId);
            return (
              <li key={cardId}>
                <div><strong>{card.title}</strong><span>{card.description}</span></div>
                <button type="button" onClick={() => onRestore(cardId)}><Plus size={16} aria-hidden="true" />추가</button>
              </li>
            );
          })}
        </ul>
      )}
    </dialog>
  );
}
