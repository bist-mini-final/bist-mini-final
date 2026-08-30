import {
  Check,
  Focus,
  Minus,
  Plus,
  X,
  type LucideIcon,
} from 'lucide-react';
import type { RefObject } from 'react';
import type { SpreadsheetResult } from './spreadsheetResultModel';

export function SpreadsheetInspectorHeader({
  icon: Icon,
  title,
  description,
  sheetCount,
  tableCount,
  regionCount,
  closeButtonRef,
  onClose,
}: {
  readonly icon: LucideIcon;
  readonly title: string;
  readonly description: string;
  readonly sheetCount: number;
  readonly tableCount: number;
  readonly regionCount: number;
  readonly closeButtonRef: RefObject<HTMLButtonElement>;
  readonly onClose: () => void;
}) {
  return (
    <header className="spreadsheet-result-modal__header">
      <span className="spreadsheet-result-modal__mark"><Icon className="h-5 w-5" /></span>
      <div className="spreadsheet-result-modal__heading">
        <div className="spreadsheet-result-modal__eyebrow">Spreadsheet Result Inspector</div>
        <h2 id="spreadsheet-result-title">{title}</h2>
        <p>{description}</p>
      </div>
      <div className="spreadsheet-result-modal__summary">
        <span>{sheetCount} sheets</span>
        <span>{tableCount} tables</span>
        <span>{regionCount} regions</span>
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
  );
}

interface SpreadsheetInspectorToolbarProps {
  readonly parsed: SpreadsheetResult;
  readonly selectedSheet: string;
  readonly showClassificationBoxes: boolean;
  readonly showCellTypeColors: boolean;
  readonly zoom: number;
  readonly imageSize: { readonly width: number; readonly height: number };
  readonly onSelectedSheetChange: (sheet: string) => void;
  readonly onToggleClassificationBoxes: () => void;
  readonly onToggleCellTypeColors: () => void;
  readonly onChangeZoom: (delta: number) => void;
  readonly onFitImage: (width: number, height: number) => void;
}

export function SpreadsheetInspectorToolbar({
  parsed,
  selectedSheet,
  showClassificationBoxes,
  showCellTypeColors,
  zoom,
  imageSize,
  onSelectedSheetChange,
  onToggleClassificationBoxes,
  onToggleCellTypeColors,
  onChangeZoom,
  onFitImage,
}: SpreadsheetInspectorToolbarProps) {
  return (
    <div className="spreadsheet-result-toolbar">
      <label>
        <span>시트</span>
        <select
          value={selectedSheet}
          onChange={(event) => onSelectedSheetChange(event.currentTarget.value)}
          onMouseDown={(event) => event.stopPropagation()}
          onClick={(event) => event.stopPropagation()}
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
      <div className="spreadsheet-result-toolbar__view-options" role="group" aria-label="결과 보기 옵션">
        <span>보기</span>
        <button
          type="button"
          role="checkbox"
          aria-checked={showClassificationBoxes}
          data-active={showClassificationBoxes ? 'true' : 'false'}
          onClick={onToggleClassificationBoxes}
        >
          <i>{showClassificationBoxes && <Check className="h-2.5 w-2.5" />}</i>
          영역 분류 박스
        </button>
        <button
          type="button"
          role="checkbox"
          aria-checked={showCellTypeColors}
          data-active={showCellTypeColors ? 'true' : 'false'}
          onClick={onToggleCellTypeColors}
        >
          <i>{showCellTypeColors && <Check className="h-2.5 w-2.5" />}</i>
          셀 타입 색상
        </button>
      </div>
      <div className="spreadsheet-result-toolbar__legend" aria-label="영역 색상 범례">
        {showClassificationBoxes && (
          <>
            <span data-region="title"><i /> 제목</span>
            <span data-region="column"><i /> 열 헤더</span>
            <span data-region="row"><i /> 행 헤더</span>
            <span data-region="data"><i /> 데이터</span>
          </>
        )}
        {showCellTypeColors && (
          <>
            <span data-cell-type="text"><i /> 텍스트</span>
            <span data-cell-type="number"><i /> 숫자</span>
            <span data-cell-type="date"><i /> 날짜</span>
            <span data-cell-type="formula"><i /> 수식</span>
          </>
        )}
      </div>
      <div className="spreadsheet-result-toolbar__zoom">
        <button type="button" onClick={() => onChangeZoom(-0.1)} aria-label="축소"><Minus className="h-3.5 w-3.5" /></button>
        <span>{Math.round(zoom * 100)}%</span>
        <button type="button" onClick={() => onChangeZoom(0.1)} aria-label="확대"><Plus className="h-3.5 w-3.5" /></button>
        <button
          type="button"
          onClick={() => imageSize.width && onFitImage(imageSize.width, imageSize.height)}
          aria-label="화면에 맞춤"
          title="화면에 맞춤"
        >
          <Focus className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}
