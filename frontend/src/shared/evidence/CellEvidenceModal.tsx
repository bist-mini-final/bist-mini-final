import {
  AlertTriangle,
  FileSpreadsheet,
  Focus,
  LoaderCircle,
  Minus,
  Plus,
  X,
} from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { CellCitation } from '../markdown/cellCitations';
import { cellEvidenceApi, type CellEvidence } from './cellEvidenceApi';
import './CellEvidenceModal.css';

interface CellEvidenceModalProps {
  readonly citation: CellCitation;
  readonly onClose: () => void;
}

function joinedHeader(values: readonly string[], fallback?: string): string {
  if (values.length > 0) return values.join(' › ');
  return fallback?.trim() || '—';
}

export function CellEvidenceModal({ citation, onClose }: CellEvidenceModalProps) {
  const [evidence, setEvidence] = useState<CellEvidence | null>(null);
  const [error, setError] = useState('');
  const [zoom, setZoom] = useState(0.8);
  const [imageReady, setImageReady] = useState(false);
  const viewportRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeButtonRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  useEffect(() => {
    const controller = new AbortController();
    setEvidence(null);
    setError('');
    setImageReady(false);
    cellEvidenceApi.resolve(citation, controller.signal)
      .then(setEvidence)
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(reason instanceof Error ? reason.message : '셀 근거를 불러오지 못했습니다.');
      });
    return () => controller.abort();
  }, [citation]);

  const bbox = evidence?.image.cell_bbox_px ?? null;
  const imageUrl = evidence?.image.rendered_available
    ? cellEvidenceApi.imageUrl(evidence)
    : '';
  const imageSize = useMemo(() => ({
    width: evidence?.image.image_width ?? 0,
    height: evidence?.image.image_height ?? 0,
  }), [evidence]);

  const fitImage = () => {
    const viewport = viewportRef.current;
    if (!viewport || !imageSize.width || !imageSize.height) return;
    const fitted = Math.min(
      1,
      Math.max(0.15, (viewport.clientWidth - 48) / imageSize.width),
      Math.max(0.15, (viewport.clientHeight - 48) / imageSize.height),
    );
    setZoom(Math.round(fitted * 20) / 20);
  };

  const focusCell = () => {
    const viewport = viewportRef.current;
    if (!viewport || !bbox) return;
    const cellCenterX = ((bbox[0] + bbox[2]) / 2) * zoom;
    const cellCenterY = ((bbox[1] + bbox[3]) / 2) * zoom;
    viewport.scrollTo({
      left: Math.max(0, cellCenterX - viewport.clientWidth / 2),
      top: Math.max(0, cellCenterY - viewport.clientHeight / 2),
      behavior: 'smooth',
    });
  };

  useEffect(() => {
    if (!imageReady || !bbox) return;
    const frame = window.requestAnimationFrame(focusCell);
    return () => window.cancelAnimationFrame(frame);
  // Focus follows both the loaded evidence and explicit zoom changes.
  }, [imageReady, bbox, zoom]); // eslint-disable-line react-hooks/exhaustive-deps

  return createPortal(
    <div
      className="cell-evidence-overlay"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        className="cell-evidence-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="cell-evidence-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="cell-evidence-modal__header">
          <span className="cell-evidence-modal__mark"><FileSpreadsheet aria-hidden="true" /></span>
          <div>
            <span>Source cell verification</span>
            <h2 id="cell-evidence-title">셀 원본 근거 검증</h2>
            <p>답변에 사용된 셀을 원본 Excel 시트 이미지에서 직접 확인합니다.</p>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            className="cell-evidence-modal__close"
            onClick={onClose}
            aria-label="근거 검증 닫기"
          >
            <X aria-hidden="true" />
          </button>
        </header>

        <div className="cell-evidence-modal__body">
          <aside className="cell-evidence-details" aria-label="셀 근거 메타데이터">
            <div className="cell-evidence-details__target">
              <span>{evidence?.sheet_name || citation.sheet}</span>
              <strong>{evidence?.cell_coord || citation.cell}</strong>
            </div>
            {!evidence && !error && (
              <div className="cell-evidence-state">
                <LoaderCircle className="cell-evidence-state__spinner" aria-hidden="true" />
                <span>인덱스와 원본 파일을 대조하고 있습니다.</span>
              </div>
            )}
            {error && (
              <div className="cell-evidence-state cell-evidence-state--error">
                <AlertTriangle aria-hidden="true" />
                <strong>근거 연결 실패</strong>
                <span>{error}</span>
              </div>
            )}
            {evidence && (
              <dl>
                <div><dt>기업</dt><dd>{evidence.company_name || citation.company || '—'}</dd></div>
                <div><dt>원본 파일</dt><dd title={evidence.file_name}>{evidence.file_name || '—'}</dd></div>
                <div><dt>행 항목</dt><dd>{joinedHeader(evidence.row_header, citation.rowHeader)}</dd></div>
                <div><dt>열 항목</dt><dd>{joinedHeader(evidence.column_header, citation.columnHeader)}</dd></div>
                <div><dt>셀 값</dt><dd className="cell-evidence-details__value">{evidence.cell_value || citation.cellValue || '—'}</dd></div>
              </dl>
            )}
            <div className="cell-evidence-details__note">
              초록 뱃지는 답변 표시용 좌표이며, 빨간 테두리가 원본 이미지에서 다시 계산한 실제 셀 영역입니다.
            </div>
          </aside>

          <div className="cell-evidence-viewer">
            <div className="cell-evidence-toolbar">
              <div>
                <strong>원본 시트</strong>
                <span>{evidence?.file_name || '근거를 확인하는 중입니다.'}</span>
              </div>
              <div className="cell-evidence-toolbar__actions">
                <button type="button" onClick={() => setZoom((value) => Math.max(0.15, value - 0.1))} aria-label="축소">
                  <Minus aria-hidden="true" />
                </button>
                <output>{Math.round(zoom * 100)}%</output>
                <button type="button" onClick={() => setZoom((value) => Math.min(2, value + 0.1))} aria-label="확대">
                  <Plus aria-hidden="true" />
                </button>
                <button type="button" onClick={fitImage} aria-label="시트 화면 맞춤">
                  <Focus aria-hidden="true" />
                  <span>맞춤</span>
                </button>
                <button type="button" onClick={focusCell} disabled={!bbox} aria-label="근거 셀로 이동">
                  <Focus aria-hidden="true" />
                  <span>근거 셀</span>
                </button>
              </div>
            </div>
            <div ref={viewportRef} className="cell-evidence-viewport">
              {evidence?.image.rendered_available && imageUrl ? (
                <div
                  className="cell-evidence-canvas"
                  style={{ width: imageSize.width * zoom, height: imageSize.height * zoom }}
                >
                  <img
                    src={imageUrl}
                    alt={`${evidence.sheet_name} 원본 시트`}
                    style={{ width: imageSize.width * zoom, height: imageSize.height * zoom }}
                    onLoad={() => {
                      setImageReady(true);
                    }}
                    onError={() => setError('원본 시트 이미지를 불러오지 못했습니다.')}
                  />
                  {bbox && (
                    <span
                      className="cell-evidence-highlight"
                      style={{
                        left: bbox[0] * zoom,
                        top: bbox[1] * zoom,
                        width: Math.max(2, (bbox[2] - bbox[0]) * zoom),
                        height: Math.max(2, (bbox[3] - bbox[1]) * zoom),
                      }}
                    >
                      <b>{evidence.cell_coord}</b>
                    </span>
                  )}
                </div>
              ) : evidence ? (
                <div className="cell-evidence-viewer__empty">
                  <AlertTriangle aria-hidden="true" />
                  <strong>원본 시트 이미지 없음</strong>
                  <p>{evidence.image.unavailable_reason || '이 파일의 시트 이미지를 찾을 수 없습니다.'}</p>
                </div>
              ) : (
                <div className="cell-evidence-viewer__empty">
                  <LoaderCircle className="cell-evidence-state__spinner" aria-hidden="true" />
                  <strong>원본 시트를 준비하는 중입니다.</strong>
                </div>
              )}
            </div>
          </div>
        </div>
      </section>
    </div>,
    document.body,
  );
}
