import { useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  cellCitationLabel,
  normalizeCellCitations,
  parseCellCitationHref,
  type CellCitation,
} from '../../../shared/markdown/cellCitations';
import { CellEvidenceModal } from '../../../shared/evidence/CellEvidenceModal';
import './MarkdownAnswer.css';

interface MarkdownAnswerProps {
  markdown: string;
}

export function normalizeMarkdownTables(markdown: string) {
  return markdown.replace(/\\+\|/g, '|').split('\n').map((line) => {
    const separatorStart = line.indexOf('|---');
    const tableStart = line.indexOf('|');
    if (separatorStart < 0 || tableStart < 0 || tableStart >= separatorStart) return line;

    const headerCells = line.slice(tableStart, separatorStart).split('|').map((cell) => cell.trim()).filter(Boolean);
    const remainingCells = line.slice(separatorStart).split('|').map((cell) => cell.trim()).filter(Boolean);
    const separatorCells = remainingCells.slice(0, headerCells.length);
    const dataCells = remainingCells.slice(headerCells.length);
    const rowCount = Math.floor(dataCells.length / headerCells.length);
    if (headerCells.length < 3 || !rowCount || !separatorCells.every((cell) => /^:?-{3,}:?$/.test(cell))) return line;

    const rows = Array.from({ length: rowCount }, (_, row) =>
      dataCells.slice(row * headerCells.length, (row + 1) * headerCells.length),
    );
    const table = [
      `| ${headerCells.join(' | ')} |`,
      `| ${separatorCells.join(' | ')} |`,
      ...rows.map((row) => `| ${row.join(' | ')} |`),
    ].join('\n');
    const remainder = dataCells.slice(rowCount * headerCells.length).join(' | ').trim();
    return `${line.slice(0, tableStart)}${table}${remainder ? `\n${remainder}` : ''}`;
  }).join('\n');
}

interface TooltipPosition {
  readonly left: number;
  readonly top: number;
  readonly placement: 'above' | 'below';
}

function CellCitationChip({
  citation,
  onOpen,
}: {
  readonly citation: CellCitation;
  readonly onOpen: (citation: CellCitation) => void;
}) {
  const anchorRef = useRef<HTMLButtonElement>(null);
  const tooltipId = useId();
  const [position, setPosition] = useState<TooltipPosition | null>(null);
  const label = cellCitationLabel(citation);
  const details = [
    ['기업', citation.company],
    ['시트', citation.sheet],
    ['셀', citation.cell],
    ['행 항목', citation.rowHeader],
    ['열 항목', citation.columnHeader],
    ['셀 값', citation.cellValue],
    ['원본 파일', citation.fileName],
  ].filter((entry): entry is [string, string] => Boolean(entry[1]));

  const showTooltip = () => {
    const rect = anchorRef.current?.getBoundingClientRect();
    if (!rect) return;
    const tooltipWidth = Math.min(352, window.innerWidth - 24);
    const left = Math.max(12, Math.min(rect.left, window.innerWidth - tooltipWidth - 12));
    const placement = rect.bottom + 220 > window.innerHeight && rect.top > 220 ? 'above' : 'below';
    setPosition({ left, top: placement === 'above' ? rect.top - 8 : rect.bottom + 8, placement });
  };
  const openEvidence = () => {
    setPosition(null);
    onOpen(citation);
  };

  return (
    <>
      <button
        type="button"
        ref={anchorRef}
        className="reader-citation nodrag nopan nowheel"
        aria-haspopup="dialog"
        aria-describedby={position ? tooltipId : undefined}
        onMouseEnter={showTooltip}
        onMouseLeave={() => setPosition(null)}
        onFocus={showTooltip}
        onBlur={() => setPosition(null)}
        onPointerDown={(event) => event.stopPropagation()}
        onMouseDown={(event) => event.stopPropagation()}
        onClick={(event) => {
          event.stopPropagation();
          openEvidence();
        }}
      >
        {label}
      </button>
      {position && createPortal(
        <aside
          id={tooltipId}
          className="reader-citation-tooltip"
          role="tooltip"
          data-placement={position.placement}
          style={{ left: position.left, top: position.top }}
        >
          <strong>{label} 셀 출처</strong>
          <dl>
            {details.map(([term, value]) => (
              <div key={term} style={{ display: 'contents' }}>
                <dt>{term}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
          <p>클릭하여 원본 시트 이미지에서 이 셀을 검증할 수 있습니다.</p>
        </aside>,
        document.body,
      )}
    </>
  );
}

export function MarkdownAnswer({ markdown }: MarkdownAnswerProps) {
  const [selectedCitation, setSelectedCitation] = useState<CellCitation | null>(null);
  return (
    <>
      <div className="reader-markdown">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            a: ({ href, children }) => {
              const citation = parseCellCitationHref(href);
              return citation
                ? <CellCitationChip citation={citation} onOpen={setSelectedCitation} />
                : <a href={href}>{children}</a>;
            },
          }}
        >
          {normalizeCellCitations(normalizeMarkdownTables(markdown))}
        </ReactMarkdown>
      </div>
      {selectedCitation && (
        <CellEvidenceModal
          citation={selectedCitation}
          onClose={() => setSelectedCitation(null)}
        />
      )}
    </>
  );
}
