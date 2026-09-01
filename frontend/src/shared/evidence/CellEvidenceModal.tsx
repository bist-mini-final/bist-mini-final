import {
  AlertTriangle,
  FileSpreadsheet,
  Focus,
  LoaderCircle,
  Minus,
  Plus,
  RotateCw,
} from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import type { SheetCitationGroup } from '../markdown/cellCitations';
import { Button, Dialog, IconButton } from '../ui';
import { useDragPan } from '../ui/useDragPan';
import { cellEvidenceApi, type CellEvidence } from './cellEvidenceApi';
import './CellEvidenceModal.css';

interface CellEvidenceModalProps {
  readonly group: SheetCitationGroup;
  readonly onClose: () => void;
}

type BoundingBox = readonly [number, number, number, number];

function evidenceBounds(items: readonly CellEvidence[]): BoundingBox | null {
  const boxes = items
    .map((item) => item.image.cell_bbox_px)
    .filter((box): box is BoundingBox => box !== null);
  if (boxes.length === 0) return null;
  return [
    Math.min(...boxes.map((box) => box[0])),
    Math.min(...boxes.map((box) => box[1])),
    Math.max(...boxes.map((box) => box[2])),
    Math.max(...boxes.map((box) => box[3])),
  ];
}

export function CellEvidenceModal({ group, onClose }: CellEvidenceModalProps) {
  const [evidence, setEvidence] = useState<readonly CellEvidence[]>([]);
  const [error, setError] = useState('');
  const [unresolvedCount, setUnresolvedCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [zoom, setZoom] = useState(0.8);
  const [imageReady, setImageReady] = useState(false);
  const [requestVersion, setRequestVersion] = useState(0);
  const viewportRef = useRef<HTMLDivElement>(null);
  const { isDragging, dragPanProps } = useDragPan(viewportRef);

  useEffect(() => {
    const controller = new AbortController();
    setEvidence([]);
    setError('');
    setUnresolvedCount(0);
    setLoading(true);
    setImageReady(false);
    setZoom(0.8);

    cellEvidenceApi.resolveMany(group.citations, controller.signal).then((resolved) => {
      if (controller.signal.aborted) return;
      setEvidence(resolved);
      setUnresolvedCount(group.citations.length - resolved.length);
      setLoading(false);
    }).catch((reason: unknown) => {
      if (controller.signal.aborted) return;
      setLoading(false);
      setError(reason instanceof Error ? reason.message : '시트 근거를 불러오지 못했습니다.');
    });
    return () => controller.abort();
  }, [group, requestVersion]);

  const primary = evidence.find((item) => item.image.rendered_available) ?? evidence[0] ?? null;
  const bounds = useMemo(() => evidenceBounds(evidence), [evidence]);
  const imageUrl = primary?.image.rendered_available ? cellEvidenceApi.imageUrl(primary) : '';
  const imageSize = useMemo(() => ({
    width: primary?.image.image_width ?? 0,
    height: primary?.image.image_height ?? 0,
  }), [primary]);

  const scrollToBounds = (target: BoundingBox, targetZoom: number) => {
    window.requestAnimationFrame(() => {
      const viewport = viewportRef.current;
      if (!viewport) return;
      const centerX = ((target[0] + target[2]) / 2) * targetZoom;
      const centerY = ((target[1] + target[3]) / 2) * targetZoom;
      viewport.scrollTo({
        left: Math.max(0, centerX - viewport.clientWidth / 2),
        top: Math.max(0, centerY - viewport.clientHeight / 2),
        behavior: 'smooth',
      });
    });
  };

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

  const focusEvidence = () => {
    const viewport = viewportRef.current;
    if (!viewport || !bounds) return;
    const width = Math.max(1, bounds[2] - bounds[0]);
    const height = Math.max(1, bounds[3] - bounds[1]);
    const fitted = Math.min(
      2,
      Math.max(0.15, (viewport.clientWidth - 96) / width),
      Math.max(0.15, (viewport.clientHeight - 96) / height),
    );
    const nextZoom = Math.round(fitted * 20) / 20;
    setZoom(nextZoom);
    scrollToBounds(bounds, nextZoom);
  };

  return (
    <Dialog
      open
      size="xl"
      className="cell-evidence-modal"
      backdropClassName="cell-evidence-overlay"
      bodyClassName="cell-evidence-modal__body"
      eyebrow="Source sheet verification"
      title={(
        <span className="cell-evidence-dialog-title">
          <span className="cell-evidence-modal__mark"><FileSpreadsheet aria-hidden="true" /></span>
          <span>시트 원본 근거 검증</span>
        </span>
      )}
      description="답변에 사용된 셀 전체를 원본 Excel 시트 이미지에서 직접 확인합니다."
      closeLabel="근거 검증 닫기"
      onClose={onClose}
    >
      <aside className="cell-evidence-details" aria-label="시트 근거 메타데이터">
        <div className="cell-evidence-details__target">
          <span>{primary?.sheet_name || group.sheet}</span>
          <strong>{group.citations.length}개 셀</strong>
        </div>
        {loading && (
          <div className="cell-evidence-state">
            <LoaderCircle className="cell-evidence-state__spinner" aria-hidden="true" />
            <span>참조 셀과 원본 파일을 대조하고 있습니다.</span>
          </div>
        )}
        {error && (
          <div className="cell-evidence-state cell-evidence-state--error">
            <AlertTriangle aria-hidden="true" />
            <strong>근거 연결 실패</strong>
            <span>{error}</span>
          </div>
        )}
        {primary && (
          <>
            <dl>
              <div><dt>기업</dt><dd>{primary.company_name || group.citations[0]?.company || '—'}</dd></div>
              <div><dt>원본 파일</dt><dd title={primary.file_name}>{primary.file_name || '—'}</dd></div>
              <div><dt>확인된 셀</dt><dd>{evidence.length}개</dd></div>
              {unresolvedCount > 0 && <div><dt>연결 실패</dt><dd>{unresolvedCount}개</dd></div>}
            </dl>
            <section className="cell-evidence-details__cells" aria-label="참조 셀 목록">
              <strong>참조 셀</strong>
              <div>
                {evidence.map((item) => (
                  <span key={`${item.index_id}:${item.sheet_name}:${item.cell_coord}`}>{item.cell_coord}</span>
                ))}
              </div>
            </section>
          </>
        )}
        <div className="cell-evidence-details__note">
          빨간 테두리는 답변 근거로 실제 선택된 셀 영역입니다. 시트는 마우스나 터치로 드래그해 이동할 수 있습니다.
        </div>
      </aside>

      <div className="cell-evidence-viewer">
        <div className="cell-evidence-toolbar">
          <div>
            <strong>원본 시트 · {evidence.length}개 근거</strong>
            <span>{primary?.file_name || '근거를 확인하는 중입니다.'}</span>
          </div>
          <div className="cell-evidence-toolbar__actions">
            <IconButton size="sm" variant="secondary" onClick={() => setZoom((value) => Math.max(0.15, value - 0.1))} aria-label="축소" disabled={!primary}>
              <Minus aria-hidden="true" />
            </IconButton>
            <output>{Math.round(zoom * 100)}%</output>
            <IconButton size="sm" variant="secondary" onClick={() => setZoom((value) => Math.min(2, value + 0.1))} aria-label="확대" disabled={!primary}>
              <Plus aria-hidden="true" />
            </IconButton>
            <Button size="sm" variant="secondary" onClick={fitImage} aria-label="시트 화면 맞춤" disabled={!imageReady}>
              <Focus aria-hidden="true" />
              <span>맞춤</span>
            </Button>
            <Button size="sm" variant="secondary" onClick={focusEvidence} disabled={!bounds || !imageReady} aria-label="근거 영역으로 이동">
              <Focus aria-hidden="true" />
              <span>근거 영역</span>
            </Button>
          </div>
        </div>
        <div
          ref={viewportRef}
          className={`cell-evidence-viewport${isDragging ? ' is-dragging' : ''}`}
          role="region"
          aria-label="원본 시트 캔버스 · 드래그하여 이동"
          {...dragPanProps}
        >
          {primary?.image.rendered_available && imageUrl ? (
            <div
              className="cell-evidence-canvas"
              style={{ width: imageSize.width * zoom, height: imageSize.height * zoom }}
            >
              <img
                src={imageUrl}
                alt={`${primary.sheet_name} 원본 시트`}
                draggable={false}
                style={{ width: imageSize.width * zoom, height: imageSize.height * zoom }}
                onLoad={() => {
                  setImageReady(true);
                  window.requestAnimationFrame(focusEvidence);
                }}
                onError={() => setError('원본 시트 이미지를 불러오지 못했습니다.')}
              />
              {evidence.map((item) => {
                const box = item.image.cell_bbox_px;
                if (!box) return null;
                return (
                  <span
                    key={`${item.index_id}:${item.sheet_name}:${item.cell_coord}`}
                    className="cell-evidence-highlight"
                    data-cell-coord={item.cell_coord}
                    style={{
                      left: box[0] * zoom,
                      top: box[1] * zoom,
                      width: Math.max(2, (box[2] - box[0]) * zoom),
                      height: Math.max(2, (box[3] - box[1]) * zoom),
                    }}
                  />
                );
              })}
            </div>
          ) : primary ? (
            <div className="cell-evidence-viewer__empty">
              <AlertTriangle aria-hidden="true" />
              <strong>원본 시트 이미지 없음</strong>
              <p>{primary.image.unavailable_reason || '이 파일의 시트 이미지를 찾을 수 없습니다.'}</p>
            </div>
          ) : error ? (
            <div className="cell-evidence-viewer__empty cell-evidence-viewer__empty--error" role="alert">
              <AlertTriangle aria-hidden="true" />
              <strong>시트 근거를 연결하지 못했습니다.</strong>
              <p>{error}</p>
              <Button size="sm" variant="secondary" onClick={() => setRequestVersion((version) => version + 1)}>
                <RotateCw aria-hidden="true" />
                다시 시도
              </Button>
            </div>
          ) : (
            <div className="cell-evidence-viewer__empty">
              <LoaderCircle className="cell-evidence-state__spinner" aria-hidden="true" />
              <strong>원본 시트를 준비하는 중입니다.</strong>
            </div>
          )}
        </div>
      </div>
    </Dialog>
  );
}
