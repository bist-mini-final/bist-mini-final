import { useMemo } from 'react';
import { createPortal } from 'react-dom';
import './SpreadsheetResultModal.css';
import {
  parseSpreadsheetResult,
  type SpreadsheetInspectorKind,
  type SpreadsheetResult,
} from './spreadsheetResultModel';
import { INSPECTOR_META } from './spreadsheetResultPresentation';
import {
  SpreadsheetInspectorHeader,
  SpreadsheetInspectorToolbar,
} from './SpreadsheetInspectorChrome';
import { SpreadsheetInspectorBody } from './SpreadsheetInspectorBody';
import { useSpreadsheetResultInspector } from './useSpreadsheetResultInspector';

interface SpreadsheetResultModalProps {
  kind: SpreadsheetInspectorKind;
  input: unknown;
  output: unknown;
  onClose: () => void;
}

/** Parses spreadsheet output before mounting the stateful inspector dialog. */
export function SpreadsheetResultModal({
  kind,
  input,
  output,
  onClose,
}: SpreadsheetResultModalProps) {
  const parsed = useMemo(() => parseSpreadsheetResult(input, output), [input, output]);
  if (!parsed) return null;
  return <SpreadsheetResultDialog kind={kind} parsed={parsed} onClose={onClose} />;
}

function SpreadsheetResultDialog({
  kind,
  parsed,
  onClose,
}: {
  readonly kind: SpreadsheetInspectorKind;
  readonly parsed: SpreadsheetResult;
  readonly onClose: () => void;
}) {
  const meta = INSPECTOR_META[kind];
  const inspector = useSpreadsheetResultInspector({
    parsed,
    defaultLayer: meta.defaultLayer,
    onClose,
  });

  return createPortal(
    <div
      className="spreadsheet-result-overlay"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        className="spreadsheet-result-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="spreadsheet-result-title"
        data-kind={kind}
      >
        <SpreadsheetInspectorHeader
          icon={meta.icon}
          title={meta.title}
          description={meta.description}
          sheetCount={parsed.sheetNames.length}
          tableCount={parsed.tables.length}
          regionCount={inspector.totalRegions}
          closeButtonRef={inspector.closeButtonRef}
          onClose={onClose}
        />
        <SpreadsheetInspectorToolbar
          parsed={parsed}
          selectedSheet={inspector.selectedSheet}
          showClassificationBoxes={inspector.showClassificationBoxes}
          showCellTypeColors={inspector.showCellTypeColors}
          zoom={inspector.zoom}
          imageSize={inspector.imageSize}
          onSelectedSheetChange={inspector.setSelectedSheet}
          onToggleClassificationBoxes={() => inspector.setShowClassificationBoxes((current) => !current)}
          onToggleCellTypeColors={inspector.toggleCellTypeColors}
          onChangeZoom={inspector.changeZoom}
          onFitImage={inspector.fitImage}
        />
        <SpreadsheetInspectorBody
          bodyStyle={inspector.bodyStyle}
          selectedSheet={inspector.selectedSheet}
          tables={inspector.sheetTables}
          selectedTable={inspector.selectedTable}
          sidebarWidth={inspector.sidebarWidth}
          viewportRef={inspector.viewportRef}
          imageError={inspector.imageError}
          imageUrl={inspector.imageUrl}
          imageSize={inspector.imageSize}
          zoom={inspector.zoom}
          showClassificationBoxes={inspector.showClassificationBoxes}
          onSelectTable={inspector.setSelectedTableKey}
          onSidebarResize={inspector.beginSidebarResize}
          onSidebarResizeKeyDown={inspector.handleSidebarResizeKeyDown}
          onImageError={() => inspector.setImageError(true)}
          onImageLoad={(width, height) => {
            inspector.setImageSize({ width, height });
            inspector.fitImage(width, height);
          }}
        />
      </section>
    </div>,
    document.body,
  );
}
