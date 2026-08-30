import {
  Columns3,
  GripVertical,
  Grid2X2,
  ListTree,
  Rows3,
  ScanSearch,
  Type,
} from 'lucide-react';
import type {
  CSSProperties,
  KeyboardEvent as ReactKeyboardEvent,
  PointerEvent as ReactPointerEvent,
  RefObject,
} from 'react';
import { useDragPan } from '../../../../shared/ui/useDragPan';
import {
  spreadsheetColumnLetter,
  spreadsheetTableKey,
  type SpreadsheetHeaderNode,
  type SpreadsheetResultTable,
} from './spreadsheetResultModel';
import {
  compactExcelRange,
  readableHeaderName,
  REGION_META,
} from './spreadsheetResultPresentation';
import { SIDEBAR_MAX_WIDTH, SIDEBAR_MIN_WIDTH } from './useSpreadsheetResultInspector';

function HeaderTreeNodes({ nodes, depth = 0 }: { nodes: SpreadsheetHeaderNode[]; depth?: number }) {
  return (
    <ul>
      {nodes.map((node) => {
        const startCoordinate = `${spreadsheetColumnLetter(node.col_start)}${node.row_start}`;
        const endCoordinate = `${spreadsheetColumnLetter(node.col_end)}${node.row_end}`;
        const coordinate = startCoordinate === endCoordinate ? startCoordinate : `${startCoordinate}–${endCoordinate}`;
        const displayName = readableHeaderName(node.name);
        const key = `${node.name}:${node.row_start}:${node.col_start}:${node.col_end}`;
        return (
          <li key={key}>
            {node.children.length > 0 ? (
              <details open={depth === 0}>
                <summary><span title={node.name}>{displayName}</span><code>{coordinate}</code></summary>
                <HeaderTreeNodes nodes={node.children} depth={depth + 1} />
              </details>
            ) : (
              <div className="spreadsheet-result-detail__tree-row">
                <span title={node.name}>{displayName}</span><code>{coordinate}</code>
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

interface SpreadsheetInspectorSidebarProps {
  readonly selectedSheet: string;
  readonly tables: readonly SpreadsheetResultTable[];
  readonly selectedTable: SpreadsheetResultTable | null;
  readonly onSelectTable: (tableKey: string) => void;
}

function SpreadsheetInspectorSidebar({
  selectedSheet,
  tables,
  selectedTable,
  onSelectTable,
}: SpreadsheetInspectorSidebarProps) {
  return (
    <aside className="spreadsheet-result-sidebar">
      <header>
        <div><h3>{selectedSheet || '시트 미선택'}</h3><p>감지 결과 {tables.length}개</p></div>
        <span>{tables.length}</span>
      </header>
      <div className="spreadsheet-result-sidebar__list">
        {tables.length === 0 && (
          <div className="spreadsheet-result-empty">
            <ScanSearch className="h-5 w-5" />
            <strong>감지된 영역이 없습니다.</strong>
            <span>이 상태도 누락 여부를 판단하는 중요한 결과입니다.</span>
          </div>
        )}
        {tables.map((table) => {
          const tableKey = spreadsheetTableKey(table);
          const active = selectedTable ? tableKey === spreadsheetTableKey(selectedTable) : false;
          return (
            <button
              key={tableKey}
              type="button"
              className="spreadsheet-result-card"
              data-active={active ? 'true' : 'false'}
              onClick={() => onSelectTable(tableKey)}
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
      {selectedTable && <SpreadsheetTableDetail table={selectedTable} />}
    </aside>
  );
}

function SpreadsheetTableDetail({ table }: { readonly table: SpreadsheetResultTable }) {
  return (
    <section className="spreadsheet-result-detail">
      <h4><ListTree className="h-3.5 w-3.5" /> 선택 영역</h4>
      <dl>
        <div><dt>Excel</dt><dd><code>{table.excel_range}</code></dd></div>
        {table.cell_bounds && (
          <>
            <div><dt>행</dt><dd>{table.cell_bounds.min_row}–{table.cell_bounds.max_row}</dd></div>
            <div><dt>열</dt><dd>{spreadsheetColumnLetter(table.cell_bounds.min_column)}–{spreadsheetColumnLetter(table.cell_bounds.max_column)}</dd></div>
          </>
        )}
      </dl>
      {table.regions.length > 0 && (
        <div className="spreadsheet-result-detail__regions">
          {table.regions.map((region) => {
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
      {table.header_tree.length > 0 && (
        <div className="spreadsheet-result-detail__tree">
          <h5><ListTree className="h-3.5 w-3.5" /> 계층 헤더</h5>
          <HeaderTreeNodes nodes={table.header_tree} />
        </div>
      )}
    </section>
  );
}

interface SpreadsheetInspectorViewportProps {
  readonly viewportRef: RefObject<HTMLDivElement>;
  readonly imageError: boolean;
  readonly imageUrl: string;
  readonly selectedSheet: string;
  readonly imageSize: { readonly width: number; readonly height: number };
  readonly zoom: number;
  readonly showClassificationBoxes: boolean;
  readonly tables: readonly SpreadsheetResultTable[];
  readonly selectedTable: SpreadsheetResultTable | null;
  readonly onImageError: () => void;
  readonly onImageLoad: (width: number, height: number) => void;
  readonly onSelectTable: (tableKey: string) => void;
}

function SpreadsheetInspectorViewport({
  viewportRef,
  imageError,
  imageUrl,
  selectedSheet,
  imageSize,
  zoom,
  showClassificationBoxes,
  tables,
  selectedTable,
  onImageError,
  onImageLoad,
  onSelectTable,
}: SpreadsheetInspectorViewportProps) {
  const { isDragging, dragPanProps } = useDragPan(viewportRef);
  return (
    <div
      ref={viewportRef}
      className={`spreadsheet-result-viewport${isDragging ? ' is-dragging' : ''}`}
      role="region"
      aria-label="스프레드시트 결과 캔버스 · 드래그하여 이동"
      {...dragPanProps}
    >
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
              draggable={false}
              onError={onImageError}
              onLoad={(event) => onImageLoad(event.currentTarget.naturalWidth, event.currentTarget.naturalHeight)}
            />
            {showClassificationBoxes && tables.flatMap((table) =>
              table.regions.map((region) => {
                const [x1, y1, x2, y2] = region.bbox_px;
                const tableKey = spreadsheetTableKey(table);
                const active = selectedTable ? tableKey === spreadsheetTableKey(selectedTable) : false;
                return (
                  <button
                    key={`${tableKey}:${region.region_id}`}
                    type="button"
                    className={`spreadsheet-result-box ${REGION_META[region.type].className}`}
                    data-active={active ? 'true' : 'false'}
                    style={{ left: x1, top: y1, width: Math.max(2, x2 - x1), height: Math.max(2, y2 - y1) }}
                    onClick={() => onSelectTable(tableKey)}
                    aria-label={`${REGION_META[region.type].label} ${region.excel_range}`}
                  >
                    <span>{REGION_META[region.type].label} · {region.excel_range}</span>
                  </button>
                );
              }),
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export interface SpreadsheetInspectorBodyProps {
  readonly bodyStyle: CSSProperties;
  readonly selectedSheet: string;
  readonly tables: readonly SpreadsheetResultTable[];
  readonly selectedTable: SpreadsheetResultTable | null;
  readonly sidebarWidth: number;
  readonly viewportRef: RefObject<HTMLDivElement>;
  readonly imageError: boolean;
  readonly imageUrl: string;
  readonly imageSize: { readonly width: number; readonly height: number };
  readonly zoom: number;
  readonly showClassificationBoxes: boolean;
  readonly onSelectTable: (tableKey: string) => void;
  readonly onSidebarResize: (event: ReactPointerEvent<HTMLButtonElement>) => void;
  readonly onSidebarResizeKeyDown: (event: ReactKeyboardEvent<HTMLButtonElement>) => void;
  readonly onImageError: () => void;
  readonly onImageLoad: (width: number, height: number) => void;
}

export function SpreadsheetInspectorBody({
  bodyStyle,
  selectedSheet,
  tables,
  selectedTable,
  sidebarWidth,
  viewportRef,
  imageError,
  imageUrl,
  imageSize,
  zoom,
  showClassificationBoxes,
  onSelectTable,
  onSidebarResize,
  onSidebarResizeKeyDown,
  onImageError,
  onImageLoad,
}: SpreadsheetInspectorBodyProps) {
  return (
    <div className="spreadsheet-result-modal__body" style={bodyStyle}>
      <SpreadsheetInspectorSidebar
        selectedSheet={selectedSheet}
        tables={tables}
        selectedTable={selectedTable}
        onSelectTable={onSelectTable}
      />
      <button
        type="button"
        className="spreadsheet-result-sidebar-resizer"
        role="slider"
        aria-label="결과 정보 패널 너비 조절"
        aria-orientation="vertical"
        aria-valuemin={SIDEBAR_MIN_WIDTH}
        aria-valuemax={SIDEBAR_MAX_WIDTH}
        aria-valuenow={sidebarWidth}
        tabIndex={0}
        onPointerDown={onSidebarResize}
        onKeyDown={onSidebarResizeKeyDown}
        title="드래그하거나 좌우 방향키로 정보 패널 너비 조절"
      >
        <GripVertical className="h-3.5 w-3.5" />
      </button>
      <SpreadsheetInspectorViewport
        viewportRef={viewportRef}
        imageError={imageError}
        imageUrl={imageUrl}
        selectedSheet={selectedSheet}
        imageSize={imageSize}
        zoom={zoom}
        showClassificationBoxes={showClassificationBoxes}
        tables={tables}
        selectedTable={selectedTable}
        onImageError={onImageError}
        onImageLoad={onImageLoad}
        onSelectTable={onSelectTable}
      />
    </div>
  );
}
