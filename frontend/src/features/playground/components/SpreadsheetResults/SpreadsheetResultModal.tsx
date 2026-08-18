import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react';
import { createPortal } from 'react-dom';
import '../../playground.css';
import {
  Check,
  Columns3,
  CloudCog,
  Focus,
  GripVertical,
  Grid2X2,
  ListTree,
  Minus,
  Network,
  Plus,
  Rows3,
  ScanSearch,
  ScanText,
  TableProperties,
  Type,
  X,
  type LucideIcon,
} from 'lucide-react';
import {
  pipelineApi,
  type SpreadsheetArtifactLayer,
} from '../../services/api';
import {
  parseSpreadsheetResult,
  spreadsheetColumnLetter,
  spreadsheetTableKey,
  type SpreadsheetHeaderNode,
  type SpreadsheetInspectorKind,
  type SpreadsheetRegionKind,
} from './spreadsheetResultModel';

interface SpreadsheetResultModalProps {
  kind: SpreadsheetInspectorKind;
  input: unknown;
  output: unknown;
  onClose: () => void;
}

const REGION_META: Record<SpreadsheetRegionKind, { label: string; className: string }> = {
  title: { label: '제목', className: 'spreadsheet-result-region--title' },
  column_header: { label: '열 헤더', className: 'spreadsheet-result-region--column' },
  row_header: { label: '행 헤더', className: 'spreadsheet-result-region--row' },
  data: { label: '데이터', className: 'spreadsheet-result-region--data' },
};

function readableHeaderName(value: string): string {
  return value.replace(/\b(\d{4}-\d{2}-\d{2}) 00:00:00\b/g, '$1');
}

function compactExcelRange(value: string): string {
  const [start, end] = value.split(':');
  return end && start === end ? start : value;
}

interface InspectorMeta {
  title: string;
  description: string;
  icon: LucideIcon;
  layers: Array<{ value: SpreadsheetArtifactLayer; label: string }>;
  defaultLayer: SpreadsheetArtifactLayer;
}

const INSPECTOR_META: Record<SpreadsheetInspectorKind, InspectorMeta> = {
  docling: {
    title: 'Docling 테이블 감지 결과',
    description: '원본 시트와 Docling 주석 이미지를 전환하며 감지한 테이블 경계를 확인합니다.',
    icon: ScanSearch,
    layers: [
      { value: 'docling', label: 'Docling 주석' },
      { value: 'rendered', label: '원본 시트' },
    ],
    defaultLayer: 'docling',
  },
  openpyxl: {
    title: 'OpenPyXL 영역 분류 결과',
    description: '셀 서식과 값 밀도로 분류한 제목·열 헤더·행 헤더·데이터 영역을 확인합니다.',
    icon: TableProperties,
    layers: [{ value: 'rendered', label: '영역 분류' }],
    defaultLayer: 'rendered',
  },
  bfs_llm: {
    title: 'BFS + LLM 테이블 구조 식별 결과',
    description: 'BFS 표 경계, LLM이 결정한 영역과 좌표 기반 계층 헤더를 함께 확인합니다.',
    icon: Network,
    layers: [{ value: 'rendered', label: 'BFS + LLM' }],
    defaultLayer: 'rendered',
  },
  local_vlm: {
    title: 'Local VLM 테이블 구조 식별 결과',
    description: '셀 타입 오버레이와 원본 시트를 전환하며 멀티모달 구조 판단을 확인합니다.',
    icon: ScanText,
    layers: [
      { value: 'typed', label: '셀 타입 오버레이' },
      { value: 'rendered', label: '원본 시트' },
    ],
    defaultLayer: 'typed',
  },
  luna_vlm: {
    title: 'Luna 전체 시트 구조 식별 결과',
    description: '후보 영역 없이 전체 시트를 분석한 결과를 셀 타입 오버레이와 원본 좌표에서 확인합니다.',
    icon: CloudCog,
    layers: [
      { value: 'typed', label: '셀 타입 오버레이' },
      { value: 'rendered', label: '원본 시트' },
    ],
    defaultLayer: 'typed',
  },
};

function HeaderTreeNodes({
  nodes,
  depth = 0,
}: {
  nodes: SpreadsheetHeaderNode[];
  depth?: number;
}) {
  return (
    <ul>
      {nodes.map((node) => {
        const startCoordinate = `${spreadsheetColumnLetter(node.col_start)}${node.row_start}`;
        const endCoordinate = `${spreadsheetColumnLetter(node.col_end)}${node.row_end}`;
        const coordinate = startCoordinate === endCoordinate
          ? startCoordinate
          : `${startCoordinate}–${endCoordinate}`;
        const displayName = readableHeaderName(node.name);
        const key = `${node.name}:${node.row_start}:${node.col_start}:${node.col_end}`;
        if (node.children.length > 0) {
          return (
            <li key={key}>
              <details open={depth === 0}>
                <summary>
                  <span title={node.name}>{displayName}</span>
                  <code>{coordinate}</code>
                </summary>
                <HeaderTreeNodes nodes={node.children} depth={depth + 1} />
              </details>
            </li>
          );
        }
        return (
          <li key={key}>
            <div className="spreadsheet-result-detail__tree-row">
              <span title={node.name}>{displayName}</span>
              <code>{coordinate}</code>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

const SIDEBAR_MIN_WIDTH = 320;
const SIDEBAR_MAX_WIDTH = 680;

type InspectorBodyStyle = CSSProperties & {
  '--spreadsheet-sidebar-width': string;
};

export function SpreadsheetResultModal({
  kind,
  input,
  output,
  onClose,
}: SpreadsheetResultModalProps) {
  const meta = INSPECTOR_META[kind];
  const InspectorIcon = meta.icon;
  const parsed = useMemo(() => parseSpreadsheetResult(input, output), [input, output]);
  const [selectedSheet, setSelectedSheet] = useState(parsed?.sheetNames[0] ?? '');
  const [selectedTableKey, setSelectedTableKey] = useState<string | null>(null);
  const [zoom, setZoom] = useState(0.6);
  const [imageSize, setImageSize] = useState({ width: 0, height: 0 });
  const [imageError, setImageError] = useState(false);
  const [imageLayer, setImageLayer] = useState<SpreadsheetArtifactLayer>(meta.defaultLayer);
  const [showClassificationBoxes, setShowClassificationBoxes] = useState(true);
  const [showCellTypeColors, setShowCellTypeColors] = useState(true);
  const [sidebarWidth, setSidebarWidth] = useState(400);
  const viewportRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const sidebarResizeCleanupRef = useRef<(() => void) | null>(null);

  const sheetTables = useMemo(
    () => parsed?.tables.filter((table) => table.sheet_name === selectedSheet) ?? [],
    [parsed, selectedSheet]
  );
  const selectedTable = sheetTables.find((table) => spreadsheetTableKey(table) === selectedTableKey)
    ?? sheetTables[0]
    ?? null;
  const totalRegions = parsed?.tables.reduce((count, table) => count + table.regions.length, 0) ?? 0;
  const supportsClassificationBoxes = kind !== 'docling';
  const supportsCellTypeColors = kind === 'local_vlm' || kind === 'luna_vlm';
  const imageUrl = parsed && selectedSheet
    ? pipelineApi.spreadsheetArtifactUrl(
        parsed.workbookHash,
        selectedSheet,
        imageLayer,
      )
    : '';

  useEffect(() => {
    closeButtonRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  useEffect(() => () => {
    sidebarResizeCleanupRef.current?.();
  }, []);

  useEffect(() => {
    const nextSheet = parsed?.sheetNames[0] ?? '';
    setSelectedSheet(nextSheet);
    setSelectedTableKey(null);
  }, [parsed]);

  useEffect(() => {
    setSelectedTableKey(sheetTables[0] ? spreadsheetTableKey(sheetTables[0]) : null);
    setImageSize({ width: 0, height: 0 });
    setImageError(false);
  }, [selectedSheet]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setImageLayer(meta.defaultLayer);
    setShowClassificationBoxes(true);
    setShowCellTypeColors(true);
  }, [kind, meta.defaultLayer]);

  useEffect(() => {
    setImageSize({ width: 0, height: 0 });
    setImageError(false);
  }, [imageLayer]);

  const fitImage = (naturalWidth: number, naturalHeight: number) => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const availableWidth = Math.max(240, viewport.clientWidth - 48);
    const availableHeight = Math.max(240, viewport.clientHeight - 48);
    const nextZoom = Math.min(1, availableWidth / naturalWidth, availableHeight / naturalHeight);
    setZoom(Math.max(0.2, Math.round(nextZoom * 20) / 20));
  };

  const changeZoom = (delta: number) => {
    setZoom((current) => Math.min(1.5, Math.max(0.2, Number((current + delta).toFixed(2)))));
  };

  const clampSidebarWidth = (width: number) => {
    const viewportMaximum = typeof window === 'undefined'
      ? SIDEBAR_MAX_WIDTH
      : Math.max(SIDEBAR_MIN_WIDTH, window.innerWidth - 440);
    return Math.min(
      Math.max(SIDEBAR_MIN_WIDTH, Math.round(width)),
      Math.min(SIDEBAR_MAX_WIDTH, viewportMaximum),
    );
  };

  const resizeSidebarBy = (delta: number) => {
    setSidebarWidth((current) => clampSidebarWidth(current + delta));
  };

  const beginSidebarResize = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    sidebarResizeCleanupRef.current?.();
    const startX = event.clientX;
    const startWidth = sidebarWidth;
    const handlePointerMove = (moveEvent: globalThis.PointerEvent) => {
      setSidebarWidth(clampSidebarWidth(startWidth + moveEvent.clientX - startX));
    };
    const cleanup = () => {
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerUp);
      window.removeEventListener('pointercancel', handlePointerUp);
      document.body.classList.remove('spreadsheet-result-is-resizing');
      sidebarResizeCleanupRef.current = null;
    };
    const handlePointerUp = () => cleanup();
    sidebarResizeCleanupRef.current = cleanup;
    document.body.classList.add('spreadsheet-result-is-resizing');
    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);
    window.addEventListener('pointercancel', handlePointerUp);
  };

  const handleSidebarResizeKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
    event.preventDefault();
    resizeSidebarBy(event.key === 'ArrowLeft' ? -24 : 24);
  };

  const bodyStyle: InspectorBodyStyle = {
    '--spreadsheet-sidebar-width': `${sidebarWidth}px`,
  };

  const toggleCellTypeColors = () => {
    const nextValue = !showCellTypeColors;
    setShowCellTypeColors(nextValue);
    setImageLayer(nextValue ? 'typed' : 'rendered');
  };

  if (!parsed) return null;

  return createPortal(
    <div className="spreadsheet-result-overlay" role="presentation" onMouseDown={onClose}>
      <section
        className="spreadsheet-result-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="spreadsheet-result-title"
        data-kind={kind}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="spreadsheet-result-modal__header">
          <span className="spreadsheet-result-modal__mark"><InspectorIcon className="h-5 w-5" /></span>
          <div className="spreadsheet-result-modal__heading">
            <div className="spreadsheet-result-modal__eyebrow">Spreadsheet Result Inspector</div>
            <h2 id="spreadsheet-result-title">{meta.title}</h2>
            <p>{meta.description}</p>
          </div>
          <div className="spreadsheet-result-modal__summary">
            <span>{parsed.sheetNames.length} sheets</span>
            <span>{parsed.tables.length} tables</span>
            {kind !== 'docling' && <span>{totalRegions} regions</span>}
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            className="spreadsheet-result-modal__close"
            onClick={onClose}
            aria-label="결과 검사 창 닫기"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="spreadsheet-result-toolbar">
          <label>
            <span>시트</span>
            <select
              value={selectedSheet}
              onChange={(event) => setSelectedSheet(event.currentTarget.value)}
            >
              {parsed.sheetNames.map((sheetName) => (
                <option key={sheetName} value={sheetName}>{sheetName}</option>
              ))}
            </select>
          </label>
          <div className="spreadsheet-result-toolbar__file">
            <strong title={parsed.fileName}>{parsed.fileName}</strong>
            <code>{parsed.workbookHash.slice(0, 12)}</code>
          </div>
          {meta.layers.length > 1 && !supportsCellTypeColors && (
            <div className="spreadsheet-result-toolbar__layers" role="group" aria-label="검사 이미지 레이어">
              {meta.layers.map((layer) => (
                <button
                  key={layer.value}
                  type="button"
                  data-active={imageLayer === layer.value ? 'true' : 'false'}
                  onClick={() => setImageLayer(layer.value)}
                >
                  {layer.label}
                </button>
              ))}
            </div>
          )}
          {(supportsClassificationBoxes || supportsCellTypeColors) && (
            <div className="spreadsheet-result-toolbar__view-options" role="group" aria-label="결과 보기 옵션">
              <span>보기</span>
              {supportsClassificationBoxes && (
                <button
                  type="button"
                  role="checkbox"
                  aria-checked={showClassificationBoxes}
                  data-active={showClassificationBoxes ? 'true' : 'false'}
                  onClick={() => setShowClassificationBoxes((current) => !current)}
                >
                  <i>{showClassificationBoxes && <Check className="h-2.5 w-2.5" />}</i>
                  영역 분류 박스
                </button>
              )}
              {supportsCellTypeColors && (
                <button
                  type="button"
                  role="checkbox"
                  aria-checked={showCellTypeColors}
                  data-active={showCellTypeColors ? 'true' : 'false'}
                  onClick={toggleCellTypeColors}
                >
                  <i>{showCellTypeColors && <Check className="h-2.5 w-2.5" />}</i>
                  셀 타입 색상
                </button>
              )}
            </div>
          )}
          <div className="spreadsheet-result-toolbar__legend" aria-label="영역 색상 범례">
            {kind === 'docling' ? (
              <span data-region="table"><i /> 테이블</span>
            ) : (
              <>
                {showClassificationBoxes && (
                  <>
                    <span data-region="title"><i /> 제목</span>
                    <span data-region="column"><i /> 열 헤더</span>
                    <span data-region="row"><i /> 행 헤더</span>
                    <span data-region="data"><i /> 데이터</span>
                  </>
                )}
                {supportsCellTypeColors && showCellTypeColors && (
                  <>
                    <span data-cell-type="text"><i /> 텍스트</span>
                    <span data-cell-type="number"><i /> 숫자</span>
                    <span data-cell-type="date"><i /> 날짜</span>
                    <span data-cell-type="formula"><i /> 수식</span>
                  </>
                )}
              </>
            )}
          </div>
          <div className="spreadsheet-result-toolbar__zoom">
            <button type="button" onClick={() => changeZoom(-0.1)} aria-label="축소"><Minus className="h-3.5 w-3.5" /></button>
            <span>{Math.round(zoom * 100)}%</span>
            <button type="button" onClick={() => changeZoom(0.1)} aria-label="확대"><Plus className="h-3.5 w-3.5" /></button>
            <button
              type="button"
              onClick={() => imageSize.width && fitImage(imageSize.width, imageSize.height)}
              aria-label="화면에 맞춤"
              title="화면에 맞춤"
            >
              <Focus className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        <div className="spreadsheet-result-modal__body" style={bodyStyle}>
          <aside className="spreadsheet-result-sidebar">
            <header>
              <div>
                <h3>{selectedSheet || '시트 미선택'}</h3>
                <p>감지 결과 {sheetTables.length}개</p>
              </div>
              <span>{sheetTables.length}</span>
            </header>
            <div className="spreadsheet-result-sidebar__list">
              {sheetTables.length === 0 && (
                <div className="spreadsheet-result-empty">
                  <ScanSearch className="h-5 w-5" />
                  <strong>감지된 영역이 없습니다.</strong>
                  <span>이 상태도 누락 여부를 판단하는 중요한 결과입니다.</span>
                </div>
              )}
              {sheetTables.map((table) => {
                const active = selectedTable ? spreadsheetTableKey(table) === spreadsheetTableKey(selectedTable) : false;
                return (
                  <button
                    key={spreadsheetTableKey(table)}
                    type="button"
                    className="spreadsheet-result-card"
                    data-active={active ? 'true' : 'false'}
                    onClick={() => setSelectedTableKey(spreadsheetTableKey(table))}
                  >
                    <span className="spreadsheet-result-card__number">{table.table_index}</span>
                    <span className="spreadsheet-result-card__content">
                      <strong>Table {table.table_index}</strong>
                      <code>{table.excel_range}</code>
                      {table.cell_bounds && (
                        <small>
                          {table.cell_bounds.max_row - table.cell_bounds.min_row + 1}행 ×{' '}
                          {table.cell_bounds.max_column - table.cell_bounds.min_column + 1}열
                        </small>
                      )}
                      {table.regions.length > 0 && (
                        <span className="spreadsheet-result-card__regions">
                          {table.regions.map((region) => (
                            <i key={region.region_id} data-region={region.type} title={`${REGION_META[region.type].label}: ${region.excel_range}`} />
                          ))}
                        </span>
                      )}
                    </span>
                  </button>
                );
              })}
            </div>
            {selectedTable && (
              <section className="spreadsheet-result-detail">
                <h4><ListTree className="h-3.5 w-3.5" /> 선택 영역</h4>
                <dl>
                  <div><dt>Excel</dt><dd><code>{selectedTable.excel_range}</code></dd></div>
                  {selectedTable.cell_bounds && (
                    <>
                      <div><dt>행</dt><dd>{selectedTable.cell_bounds.min_row}–{selectedTable.cell_bounds.max_row}</dd></div>
                      <div><dt>열</dt><dd>{spreadsheetColumnLetter(selectedTable.cell_bounds.min_column)}–{spreadsheetColumnLetter(selectedTable.cell_bounds.max_column)}</dd></div>
                    </>
                  )}
                </dl>
                {selectedTable.regions.length > 0 && (
                  <div className="spreadsheet-result-detail__regions">
                    {selectedTable.regions.map((region) => {
                      const Icon = region.type === 'title'
                        ? Type
                        : region.type === 'column_header'
                          ? Columns3
                          : region.type === 'row_header'
                            ? Rows3
                            : Grid2X2;
                      return (
                        <div key={region.region_id} data-region={region.type}>
                          <Icon className="h-3.5 w-3.5" />
                          <span>{REGION_META[region.type].label}</span>
                          <code title={region.excel_range}>{compactExcelRange(region.excel_range)}</code>
                        </div>
                      );
                    })}
                  </div>
                )}
                {selectedTable.header_tree.length > 0 && (
                  <div className="spreadsheet-result-detail__tree">
                    <h5><ListTree className="h-3.5 w-3.5" /> 계층 헤더</h5>
                    <HeaderTreeNodes nodes={selectedTable.header_tree} />
                  </div>
                )}
              </section>
            )}
          </aside>

          <div
            className="spreadsheet-result-sidebar-resizer"
            role="separator"
            aria-label="결과 정보 패널 너비 조절"
            aria-orientation="vertical"
            aria-valuemin={SIDEBAR_MIN_WIDTH}
            aria-valuemax={SIDEBAR_MAX_WIDTH}
            aria-valuenow={sidebarWidth}
            tabIndex={0}
            onPointerDown={beginSidebarResize}
            onKeyDown={handleSidebarResizeKeyDown}
            title="드래그하거나 좌우 방향키로 정보 패널 너비 조절"
          >
            <GripVertical className="h-3.5 w-3.5" />
          </div>

          <div ref={viewportRef} className="spreadsheet-result-viewport">
            {imageError ? (
              <div className="spreadsheet-result-image-error">
                <ScanSearch className="h-6 w-6" />
                <strong>시트 이미지를 불러올 수 없습니다.</strong>
                <span>해당 구조 식별 모듈을 다시 실행해 검사 이미지를 생성하세요.</span>
              </div>
            ) : (
              <div
                className="spreadsheet-result-stage-shell"
                style={{
                  width: imageSize.width ? imageSize.width * zoom : undefined,
                  height: imageSize.height ? imageSize.height * zoom : undefined,
                }}
              >
                <div
                  className="spreadsheet-result-stage"
                  style={{
                    width: imageSize.width || undefined,
                    height: imageSize.height || undefined,
                    transform: `scale(${zoom})`,
                  }}
                >
                  <img
                    src={imageUrl}
                    alt={`${selectedSheet} Excel 렌더링`}
                    onError={() => setImageError(true)}
                    onLoad={(event) => {
                      const image = event.currentTarget;
                      setImageSize({ width: image.naturalWidth, height: image.naturalHeight });
                      fitImage(image.naturalWidth, image.naturalHeight);
                    }}
                  />
                  {showClassificationBoxes && kind === 'docling' && imageLayer === 'rendered' && sheetTables.map((table) => {
                    if (!table.bbox_px) return null;
                    const [x1, y1, x2, y2] = table.bbox_px;
                    const active = selectedTable ? spreadsheetTableKey(table) === spreadsheetTableKey(selectedTable) : false;
                    return (
                      <button
                        key={spreadsheetTableKey(table)}
                        type="button"
                        className="spreadsheet-result-box spreadsheet-result-box--table"
                        data-active={active ? 'true' : 'false'}
                        style={{ left: x1, top: y1, width: x2 - x1, height: y2 - y1 }}
                        onClick={() => setSelectedTableKey(spreadsheetTableKey(table))}
                        aria-label={`Table ${table.table_index} ${table.excel_range}`}
                      >
                        <span>Table {table.table_index} · {table.excel_range}</span>
                      </button>
                    );
                  })}
                  {showClassificationBoxes && kind !== 'docling' && sheetTables.flatMap((table) =>
                    table.regions.map((region) => {
                      const [x1, y1, x2, y2] = region.bbox_px;
                      const active = selectedTable ? spreadsheetTableKey(table) === spreadsheetTableKey(selectedTable) : false;
                      return (
                        <button
                          key={`${spreadsheetTableKey(table)}:${region.region_id}`}
                          type="button"
                          className={`spreadsheet-result-box ${REGION_META[region.type].className}`}
                          data-active={active ? 'true' : 'false'}
                          style={{ left: x1, top: y1, width: Math.max(2, x2 - x1), height: Math.max(2, y2 - y1) }}
                          onClick={() => setSelectedTableKey(spreadsheetTableKey(table))}
                          aria-label={`${REGION_META[region.type].label} ${region.excel_range}`}
                        >
                          <span>{REGION_META[region.type].label} · {region.excel_range}</span>
                        </button>
                      );
                    })
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </section>
    </div>,
    document.body
  );
}
