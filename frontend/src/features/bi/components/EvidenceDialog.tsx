import { useEffect, useRef } from 'react';
import { ExternalLink, FileSpreadsheet, X } from 'lucide-react';
import type { BiEvidence, BiMaterializationSource } from '../types';

interface EvidenceDialogProps {
  readonly cardTitle: string;
  readonly evidence: readonly BiEvidence[];
  readonly source: BiMaterializationSource;
  readonly snapshotId: string;
  readonly onClose: () => void;
}

export function EvidenceDialog({ cardTitle, evidence, source, snapshotId, onClose }: EvidenceDialogProps) {
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
            <div>
              <strong>{item.sheetName}!{item.cellCoord}</strong>
              <span>{item.sourceText}</span>
              <a
                href={`/api/spreadsheet-artifacts/${encodeURIComponent(source.workbookHash)}/sheets/${encodeURIComponent(item.sheetName)}?layer=rendered`}
                target="_blank"
                rel="noreferrer"
              >
                <ExternalLink size={13} aria-hidden="true" />원본 시트 열기
              </a>
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
