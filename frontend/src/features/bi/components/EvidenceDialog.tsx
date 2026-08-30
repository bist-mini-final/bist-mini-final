import { FileSpreadsheet, X } from 'lucide-react';
import { IconButton } from '../../../shared/ui';
import type { BiEvidence, BiMaterializationSource } from '../types';
import { useModalDialog } from './useModalDialog';

interface EvidenceDialogProps {
  readonly cardTitle: string;
  readonly evidence: readonly BiEvidence[];
  readonly source: BiMaterializationSource;
  readonly snapshotId: string;
  readonly onClose: () => void;
}

export function EvidenceDialog({ cardTitle, evidence, source, snapshotId, onClose }: EvidenceDialogProps) {
  const dialogRef = useModalDialog();

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
        <IconButton variant="ghost" aria-label="근거 닫기" onClick={onClose}><X size={18} aria-hidden="true" /></IconButton>
      </div>
      <ul className="bi-evidence-list">
        {evidence.map((item) => (
          <li key={item.cellId}>
            <FileSpreadsheet size={18} aria-hidden="true" />
            <div>
              <strong>{item.sheetName}!{item.cellCoord}</strong>
              <span>{item.sourceText}</span>
            </div>
          </li>
        ))}
      </ul>
      <p className="bi-dialog__note" title={source.workbookHash}>
        파일 {source.fileName} · 스냅샷 {snapshotId}
      </p>
    </dialog>
  );
}
