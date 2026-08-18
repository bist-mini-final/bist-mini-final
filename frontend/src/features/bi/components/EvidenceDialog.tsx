import { useEffect, useRef } from 'react';
import { FileSpreadsheet, X } from 'lucide-react';
import type { BiEvidence } from '../types';

interface EvidenceDialogProps {
  readonly cardTitle: string;
  readonly evidence: readonly BiEvidence[];
  readonly onClose: () => void;
}

export function EvidenceDialog({ cardTitle, evidence, onClose }: EvidenceDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    if (dialogRef.current && !dialogRef.current.open) dialogRef.current.showModal();
  }, []);

  return (
    <dialog
      ref={dialogRef}
      className="bi-dialog"
      aria-labelledby="bi-evidence-title"
      onClose={onClose}
      onCancel={(event) => { event.preventDefault(); onClose(); }}
    >
      <div className="bi-dialog__header">
        <div>
          <span className="bi-dialog__eyebrow">EVIDENCE</span>
          <h2 id="bi-evidence-title">{cardTitle} 근거</h2>
        </div>
        <button type="button" aria-label="근거 닫기" onClick={onClose}><X size={18} aria-hidden="true" /></button>
      </div>
      <ul className="bi-evidence-list">
        {evidence.map((item) => (
          <li key={item.cellId}>
            <FileSpreadsheet size={18} aria-hidden="true" />
            <div><strong>{item.sheetName}!{item.cellCoord}</strong><span>{item.sourceText}</span></div>
          </li>
        ))}
      </ul>
      <p className="bi-dialog__note">실제 파일 연결 전 fixture 근거 위치를 표시합니다.</p>
    </dialog>
  );
}
